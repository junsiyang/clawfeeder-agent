import json
import asyncio
import httpx
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple
from .api import APIClient
from .crypto import Crypto
from .storage import Storage

logger = logging.getLogger(__name__)


class ValidationRule:
    """Validation rule for keep-alive response check."""

    def __init__(
        self,
        url: str,
        method: str = "GET",
        expected_status: int = 200,
        expected_json_path: Optional[str] = None,
        json_operator: str = "exists",
        expected_json_value: Optional[str] = None,
    ):
        self.url = url
        self.method = method.upper()
        self.expected_status = expected_status
        self.expected_json_path = expected_json_path
        self.json_operator = json_operator
        self.expected_json_value = expected_json_value


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
        3. Fetch domain rule if available
        4. Execute HTTP request with dual validation
        5. Save to local storage
        6. Report status
        Returns: 'active' or 'expired'
        """
        task_id = task["id"]
        domain = task.get("domain", "unknown")

        logger.info(f"Executing task {task_id} for {domain}")

        # Step 1: Get full blob if needed
        if "encrypted_data" not in task:
            blob = await self.api.get(f"/api/v1/cookies/{task_id}")
            encrypted_data = blob["encrypted_data"]
        else:
            encrypted_data = task["encrypted_data"]

        # Step 2: Parse and decrypt
        if isinstance(encrypted_data, str):
            encrypted_payload = json.loads(encrypted_data)
        else:
            encrypted_payload = encrypted_data

        decrypted = self.crypto.decrypt(encrypted_payload)

        # Step 3: Fetch domain rule (if available)
        rule = await self._fetch_domain_rule(domain)

        # Step 4: Execute keep-alive request with validation
        status = await self._execute_keepalive_with_validation(decrypted, domain, rule)

        # Step 5: Save to local storage
        self.storage.save_cookies(domain, {
            "domain": domain,
            "note": task.get("note"),
            "cookies": decrypted.get("cookies", []),
            "capturedAt": task.get("captured_at") or datetime.utcnow().isoformat(),
            "keepAlive": decrypted.get("keepAlive", {})
        })

        # Step 6: Report status
        await self.api.patch(f"/api/v1/cookies/{task_id}/status", {
            "status": status,
            "last_checked_at": datetime.utcnow().isoformat()
        })

        logger.info(f"Task {task_id} completed with status: {status}")
        return status

    async def _fetch_domain_rule(self, domain: str) -> Optional[ValidationRule]:
        """Fetch domain rule from API if available."""
        try:
            response = await self.api.get(f"/api/v1/domain-rules/{domain}")
            if response and response.get("keep_alive_url"):
                rule = ValidationRule(
                    url=response["keep_alive_url"],
                    method=response.get("method", "GET"),
                    expected_status=response.get("expected_status", 200),
                    expected_json_path=response.get("expected_json_path"),
                    json_operator=response.get("json_operator", "exists"),
                    expected_json_value=response.get("expected_json_value"),
                )
                logger.info(
                    f"Domain rule for {domain}: {rule.method} {rule.url} "
                    f"(expect {rule.expected_status}, {rule.json_operator} {rule.expected_json_path}"
                    f"{'=' + rule.expected_json_value if rule.expected_json_value else ''})"
                )
                return rule
            logger.info(f"No domain rule configured for {domain}")
        except Exception as e:
            logger.warning(f"Failed to fetch domain rule for {domain}: {e}")
        return None

    async def _execute_keepalive_with_validation(
        self,
        decrypted: dict,
        domain: str,
        rule: Optional[ValidationRule]
    ) -> str:
        """
        Execute HTTP keep-alive request with dual validation engine.
        Retries up to 3 times with exponential backoff on transient errors.
        Returns 'active' or 'expired'.
        """
        cookies = decrypted.get("cookies", [])

        if not cookies:
            logger.debug(f"No cookies for {domain}")
            return "active"

        # Build cookie header from cookies
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

        # Determine URL and method
        if rule:
            url = rule.url
            method = rule.method
        else:
            # No domain rule: fall back to legacy keepAlive config if present,
            # otherwise skip — don't hit https://{domain}/ blindly.
            keepalive = decrypted.get("keepAlive", {})
            url = keepalive.get("url")
            if not url:
                logger.info(f"No keep-alive rule configured for {domain}, skipping")
                return "active"
            method = keepalive.get("method", "GET").upper()

        headers = {"Cookie": cookie_str}

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0, verify=False, follow_redirects=True) as client:
                    if method == "GET":
                        response = await client.get(url, headers=headers)
                    elif method == "POST":
                        response = await client.post(url, headers=headers)
                    else:
                        response = await client.request(method, url, headers=headers)

                    # Server error (5xx) — retry
                    if response.status_code >= 500 and attempt < max_retries:
                        logger.warning(f"Server error {response.status_code} for {domain} (attempt {attempt}/{max_retries})")
                        await asyncio.sleep(2 ** attempt)
                        continue

                    body_preview = response.text[:500] if response.text else "(empty)"
                    logger.info(
                        f"Keep-alive {method} {url} for {domain} → HTTP {response.status_code} "
                        f"| body: {body_preview}"
                    )

                    # Dual validation
                    ok, message = self.validate_response(response, rule)
                    if ok:
                        logger.info(f"Validation PASSED for {domain}: {message}")
                    else:
                        logger.warning(f"Validation FAILED for {domain}: {message}")

                    return "active" if ok else "expired"

            except httpx.TimeoutException:
                logger.warning(f"Timeout for {domain} (attempt {attempt}/{max_retries})")
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return "timeout"
            except Exception as e:
                logger.error(f"Error for {domain} (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return "timeout"

        return "timeout"

    def validate_response(
        self,
        response: httpx.Response,
        rule: Optional[ValidationRule]
    ) -> Tuple[bool, str]:
        """
        Dual validation engine:
        1. Status code validation (mandatory)
        2. JSON path validation (optional)

        Returns: (is_valid, message)
        """
        # 1. Status code validation (mandatory)
        if rule and rule.expected_status:
            # With rule: exact match against configured status
            if response.status_code != rule.expected_status:
                return False, f"状态码不匹配: {response.status_code} != {rule.expected_status}"
        else:
            # Without rule: accept any 2xx as active
            if not (200 <= response.status_code < 300):
                return False, f"状态码不在2xx范围: {response.status_code}"

        # 2. If no JSON path validation, consider it active
        if not rule or not rule.expected_json_path:
            return True, "存活"

        # 3. Try to parse JSON and extract value
        try:
            json_data = response.json()
            actual_value = self._extract_json_path(json_data, rule.expected_json_path)
        except Exception as e:
            return False, f"JSON解析失败: {str(e)}"

        # 4. Apply operator validation
        if rule.json_operator == "exists":
            ok = actual_value is not None
        elif rule.json_operator == "eq":
            ok = str(actual_value) == str(rule.expected_json_value)
        elif rule.json_operator == "contains":
            ok = str(rule.expected_json_value).lower() in str(actual_value).lower()
        else:
            ok = actual_value is not None

        if ok:
            return True, f"JSON验证通过: {rule.json_operator} {rule.expected_json_path}"
        else:
            return False, f"JSON验证失败: {rule.json_operator} {rule.expected_json_path}"

    def _extract_json_path(self, data, path: str):
        """
        Extract value from JSON data using dot notation path.
        Supports nested objects and array indexing.
        """
        keys = path.split('.')
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list):
                try:
                    idx = int(key)
                    current = current[idx] if idx < len(current) else None
                except ValueError:
                    return None
            else:
                return None
            if current is None:
                return None
        return current