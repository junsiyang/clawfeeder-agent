import asyncio
import logging
from typing import List, Dict, Callable, Awaitable, Optional
from .api import APIClient

class HeartbeatPoller:
    def __init__(
        self,
        api_client: APIClient,
        device_id: str,
        device_name: str,
        interval: int = 60,
        logger: Optional[logging.Logger] = None
    ):
        self.api = api_client
        self.device_id = device_id
        self.device_name = device_name
        self.interval = interval
        self._stopping = False
        self.logger = logger or logging.getLogger(__name__)

    async def poll(self) -> List[Dict]:
        """POST /api/v1/agent/heartbeat and return available tasks"""
        response = await self.api.post("/api/v1/agent/heartbeat", {
            "device_id": self.device_id,
            "device_name": self.device_name
        })
        return response.get("tasks", [])

    async def run(self, callback: Callable[[Dict], Awaitable[None]]):
        """Run heartbeat loop, call callback for each task"""
        self.logger.info(f"Starting with {self.interval}s interval")
        while not self._stopping:
            try:
                tasks = await self.poll()
                if tasks:
                    self.logger.info(f"Received {len(tasks)} tasks")
                else:
                    self.logger.debug("No tasks, sleeping")
                for task in tasks:
                    if self._stopping:
                        break
                    try:
                        await callback(task)
                    except Exception as e:
                        self.logger.error(f"Task execution error: {e}")
            except Exception as e:
                self.logger.error(f"Poll error: {e}")

            if not self._stopping:
                await asyncio.sleep(self.interval)

        self.logger.info("Stopped")

    def stop(self):
        """Signal the poller to stop gracefully"""
        self.logger.info("Shutting down")
        self._stopping = True
