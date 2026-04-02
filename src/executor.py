import httpx
from datetime import datetime
from typing import Dict
from .api import APIClient
from .crypto import Crypto
from .storage import Storage

class TaskExecutor:
    def __init__(self, api_client: APIClient, crypto: Crypto, storage: Storage):
        self.api = api_client
        self.crypto = crypto
        self.storage = storage

    async def execute(self, task: Dict) -> str:
        """
        Execute a keep-alive task:
        1. Get full blob if not in task
        2. Decrypt payload
        3. Execute HTTP request
        4. Save to local storage
        5. Report status
        Returns: 'active' or 'expired'
        """
        task_id = task["id"]
        domain = task.get("domain", "unknown")

        print(f"[Executor] Executing task {task_id} for {domain}")

        # Step 1: Get full blob if needed
        if "encrypted_data" not in task:
            blob = await self.api.get(f"/api/v1/cookies/{task_id}")
            encrypted_data = blob["encrypted_data"]
        else:
            encrypted_data = task["encrypted_data"]

        # Step 2: Parse and decrypt
        import json
        if isinstance(encrypted_data, str):
            encrypted_payload = json.loads(encrypted_data)
        else:
            encrypted_payload = encrypted_data

        decrypted = self.crypto.decrypt(encrypted_payload)

        # Step 3: Execute keep-alive request
        status = await self._execute_keepalive(decrypted, domain)

        # Step 4: Save to local storage
        self.storage.save_cookies(domain, {
            "domain": domain,
            "cookies": decrypted.get("cookies", []),
            "capturedAt": datetime.utcnow().isoformat(),
            "keepAlive": decrypted.get("keepAlive", {})
        })

        # Step 5: Report status
        await self.api.patch(f"/api/v1/cookies/{task_id}/status", {
            "status": status,
            "last_checked_at": datetime.utcnow().isoformat()
        })

        print(f"[Executor] Task {task_id} completed with status: {status}")
        return status

    async def _execute_keepalive(self, decrypted: dict, domain: str) -> str:
        """
        Execute HTTP keep-alive request based on decrypted config.
        Returns 'active' or 'expired'.
        """
        cookies = decrypted.get("cookies", [])

        if not cookies:
            print(f"[Executor] No cookies for {domain}")
            return "active"

        # Find the keep-alive config (if any)
        keepalive = decrypted.get("keepAlive", {})

        # Build cookie header from cookies
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

        url = keepalive.get("url", f"https://{domain}/")
        method = keepalive.get("method", "GET").upper()
        headers = keepalive.get("headers", {})
        headers["Cookie"] = cookie_str

        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                if method == "GET":
                    response = await client.get(url, headers=headers)
                elif method == "POST":
                    response = await client.post(url, headers=headers)
                else:
                    response = await client.request(method, url, headers=headers)

                if response.status_code in (200, 201, 204):
                    return "active"
                elif response.status_code in (401, 403):
                    return "expired"
                else:
                    return "active"  # Other errors, keep trying
        except httpx.TimeoutException:
            print(f"[Executor] Timeout for {domain}")
            return "active"
        except Exception as e:
            print(f"[Executor] Error for {domain}: {e}")
            return "active"