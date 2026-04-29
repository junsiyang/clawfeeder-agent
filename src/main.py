import asyncio
import argparse
import logging
import os
import signal
from pathlib import Path
from .config import Config
from .api import APIClient
from .heartbeat import HeartbeatPoller
from .crypto import Crypto
from .executor import TaskExecutor
from .storage import Storage


DEFAULT_CONFIG = str(Path.home() / ".clawfeeder" / "config.yaml")


async def main():
    parser = argparse.ArgumentParser(description="ClawFeeder Agent")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Config file path")
    parser.add_argument("--device-id", help="Override device ID")
    parser.add_argument("--device-name", help="Override device name")
    parser.add_argument("--api-key", help="API key for authentication (format: cf_agt_...)")
    parser.add_argument("--setup", action="store_true", help="Run interactive setup wizard")
    args = parser.parse_args()

    if args.setup:
        from .setup import run_setup
        run_setup()
        return

    if not Path(args.config).exists():
        print(f"No config found at {args.config}, starting setup wizard...\n")
        from .setup import run_setup
        run_setup()
        if not Path(args.config).exists():
            return

    config = Config(args.config)

    # Setup logging
    log_dir = Path("~/.clawfeeder/logs").expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "agent.log"

    # Configure root logger so all src.* module loggers also write to file/console
    formatter = logging.Formatter(
        fmt=f"%(asctime)s [PID:%(process)d] [%(name)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    # Clear any pre-existing handlers to avoid duplicate log lines on reload
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    logger = logging.getLogger("agent")

    # Authentication: API key directly (no login needed)
    api_key = args.api_key or config._data.get("auth", {}).get("api_key")

    if not api_key:
        raise ValueError("API key required: --api-key argument or 'auth.api_key' in config.yaml")

    # Master key for E2EE decryption (same as before - from config/environment)
    master_key = config.master_key
    if not master_key:
        raise ValueError("Master key required: MASTER_KEY env var or 'master_key' in config.yaml")

    api = APIClient(base_url=config.api_base_url, api_key=api_key)

    crypto = Crypto(master_key)
    storage = Storage(config.data_dir, config.expired_dir)
    executor = TaskExecutor(api, crypto, storage)

    poller = HeartbeatPoller(
        api_client=api,
        device_id=args.device_id or config.device_id,
        device_name=args.device_name or config.device_name,
        interval=config.heartbeat_interval,
        domains=config.sync_domains,
        logger=logger
    )

    # Setup graceful shutdown handlers
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def shutdown_handler():
        logger.info("Received shutdown signal")
        poller.stop()
        shutdown_event.set()

    # Register signal handlers (SIGTERM for systemd, SIGINT for Ctrl+C)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, shutdown_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    logger.info("ClawFeeder Agent starting")
    logger.info(f"API: {config.api_base_url}")
    logger.info(f"Device: {config.device_id}")
    if config.sync_domains:
        logger.info(f"Sync domains: {', '.join(config.sync_domains)}")
    else:
        logger.info("Sync domains: all")

    sync_domains = config.sync_domains

    async def gc_loop():
        """Run GC independently every 5 minutes, regardless of task activity"""
        while not shutdown_event.is_set():
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=300)
                break  # shutdown signaled
            except asyncio.TimeoutError:
                pass  # 5 min elapsed, run GC
            try:
                await run_gc(storage, api, sync_domains)
            except Exception as e:
                logger.error(f"GC loop error: {e}")

    try:
        heartbeat_task = asyncio.create_task(poller.run(executor.execute))
        gc_task = asyncio.create_task(gc_loop())

        # Wait for shutdown signal
        await shutdown_event.wait()

        heartbeat_task.cancel()
        gc_task.cancel()
        try:
            await asyncio.gather(heartbeat_task, gc_task, return_exceptions=True)
        except asyncio.CancelledError:
            pass

    finally:
        await api.close()
        logger.info("Shutdown complete")


_gc_logger = logging.getLogger("agent")


async def run_gc(storage: Storage, api: APIClient, sync_domains: list = None):
    """Fetch cloud state and run garbage collection"""
    try:
        response = await api.get("/api/v1/cookies")
        cloud_cookies = response.get("cookies", [])
        cloud_domains = [c["domain"] for c in cloud_cookies if c.get("status") == "active"]
        if sync_domains:
            cloud_domains = [d for d in cloud_domains if d in sync_domains]
        await storage.garbage_collect(cloud_domains)
    except Exception as e:
        _gc_logger.error(f"GC error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
