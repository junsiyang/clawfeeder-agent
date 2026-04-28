import httpx
from typing import Dict, Any, Optional

class APIClient:
    def __init__(self, base_url: str, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            timeout=30.0,
            trust_env=False,
            limits=httpx.Limits(
                max_keepalive_connections=5,
                keepalive_expiry=30,
            ),
            transport=httpx.AsyncHTTPTransport(retries=2),
        )

    def set_api_key(self, api_key: str):
        self._api_key = api_key

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def post(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """POST request"""
        response = await self._client.post(
            f"{self.base_url}{path}",
            json=data,
            headers=self._headers()
        )
        response.raise_for_status()
        return response.json()

    async def get(self, path: str) -> Dict[str, Any]:
        """GET request"""
        response = await self._client.get(
            f"{self.base_url}{path}",
            headers=self._headers()
        )
        response.raise_for_status()
        return response.json()

    async def patch(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """PATCH request"""
        response = await self._client.patch(
            f"{self.base_url}{path}",
            json=data,
            headers=self._headers()
        )
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self._client.aclose()
