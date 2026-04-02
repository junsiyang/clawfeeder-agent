import asyncio
import argparse
import signal
from .config import Config
from .api import APIClient
from .heartbeat import HeartbeatPoller
from .crypto import Crypto
from .executor import TaskExecutor
from .storage import Storage

async def login(api: APIClient, email: str, password: str) -> str:
    """Login to get API key"""
    response = await api.post("/api/v1/login", {
        "email": email,
        "password": password
    })
    return response["api_key"]

async def main():
    parser = argparse.ArgumentParser(description="ClawFeeder Agent")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    parser.add_argument("--device-id", help="Override device ID")
    parser.add_argument("--device-name", help="Override device name")
    parser.add_argument("--email", help="Email for authentication")
    parser.add_argument("--password", help="Password for authentication (also used for E2EE)")
    args = parser.parse_args()

    config = Config(args.config)

    # Authentication: email + password
    email = args.email or config._data.get("auth", {}).get("email")
    password = args.password or config._data.get("auth", {}).get("password")

    if not email or not password:
        raise ValueError("Email and password required: --email and --password (or set in config.yaml)")

    api = APIClient(base_url=config.api_base_url)

    # Login to get API key
    print("[Main] Logging in...")
    api_key = await login(api, email, password)
    api.set_api_key(api_key)
    print("[Main] Login successful")

    # Password is used for both authentication and E2EE key derivation
    crypto = Crypto(password)
    storage = Storage(config.data_dir, config.expired_dir)
    executor = TaskExecutor(api, crypto, storage)

    poller = HeartbeatPoller(
        api_client=api,
        device_id=args.device_id or config.device_id,
        device_name=args.device_name or config.device_name,
        interval=config.heartbeat_interval
    )

    # Setup graceful shutdown handlers
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def shutdown_handler():
        print("[Main] Received shutdown signal...")
        poller.stop()
        shutdown_event.set()

    # Register signal handlers (SIGTERM for systemd, SIGINT for Ctrl+C)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, shutdown_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    print("[Main] ClawFeeder Agent starting...")
    print(f"[Main] API: {config.api_base_url}")
    print(f"[Main] Device: {config.device_id}")

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
        print("[Main] Shutdown complete")

async def run_gc(storage: Storage, api: APIClient):
    """Fetch cloud state and run garbage collection"""
    try:
        response = await api.get("/api/v1/cookies")
        cloud_cookies = response.get("cookies", [])
        cloud_domains = [c["domain"] for c in cloud_cookies if c.get("status") == "active"]
        await storage.garbage_collect(cloud_domains)
    except Exception as e:
        print(f"[GC] Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
