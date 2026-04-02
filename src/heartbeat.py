import asyncio
from typing import List, Dict, Callable, Awaitable
from .api import APIClient

class HeartbeatPoller:
    def __init__(
        self,
        api_client: APIClient,
        device_id: str,
        device_name: str,
        interval: int = 60
    ):
        self.api = api_client
        self.device_id = device_id
        self.device_name = device_name
        self.interval = interval
        self._stopping = False

    async def poll(self) -> List[Dict]:
        """POST /api/v1/agent/heartbeat and return available tasks"""
        response = await self.api.post("/api/v1/agent/heartbeat", {
            "device_id": self.device_id,
            "device_name": self.device_name
        })
        return response.get("tasks", [])

    async def run(self, callback: Callable[[Dict], Awaitable[None]]):
        """Run heartbeat loop, call callback for each task"""
        print(f"[Heartbeat] Starting with {self.interval}s interval")
        while not self._stopping:
            try:
                tasks = await self.poll()
                if tasks:
                    print(f"[Heartbeat] Received {len(tasks)} tasks")
                else:
                    print(f"[Heartbeat] No tasks, sleeping...")
                for task in tasks:
                    if self._stopping:
                        break
                    try:
                        await callback(task)
                    except Exception as e:
                        print(f"[Heartbeat] Task execution error: {e}")
            except Exception as e:
                print(f"[Heartbeat] Poll error: {e}")

            if not self._stopping:
                await asyncio.sleep(self.interval)

        print("[Heartbeat] Stopped")

    def stop(self):
        """Signal the poller to stop gracefully"""
        print("[Heartbeat] Shutting down...")
        self._stopping = True
