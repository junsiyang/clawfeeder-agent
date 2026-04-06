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


async def main():
    parser = argparse.ArgumentParser(description="ClawFeeder Agent")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    parser.add_argument("--device-id", help="Override device ID")
    parser.add_argument("--device-name", help="Override device name")
    parser.add_argument("--api-key", help="API key for authentication (format: cf_agt_...)")
    args = parser.parse_args()

    config = Config(args.config)

    # Setup logging
    log_dir = Path("~/.clawfeeder/logs").expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "agent.log"

    # Create agent-specific logger with PID
    pid = os.getpid()
    logger = logging.getLogger(f"agent.{config.device_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Format with PID
    formatter = logging.Formatter(
        fmt=f"%(asctime)s [PID:%(process)d] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

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

    # Wrap to also run GC periodically
    gc_counter = 0
    async def wrapped_callback(task):
        nonlocal gc_counter
        await executor.execute(task)
        gc_counter += 1
        if gc_counter >= 5:  # GC every 5 heartbeat cycles
            await run_gc(storage, api)
            gc_counter = 0

    try:
        # Run heartbeat in background
        heartbeat_task = asyncio.create_task(poller.run(wrapped_callback))

        # Wait for shutdown signal
        await shutdown_event.wait()

        # Cancel heartbeat and wait for current task to finish
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

    finally:
        await api.close()
        logger.info("Shutdown complete")


async def run_gc(storage: Storage, api: APIClient):
    """Fetch cloud state and run garbage collection"""
    try:
        response = await api.get("/api/v1/cookies")
        cloud_cookies = response.get("cookies", [])
        cloud_domains = [c["domain"] for c in cloud_cookies if c.get("status") == "active"]
        await storage.garbage_collect(cloud_domains)
    except Exception as e:
        logger.error(f"GC error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
