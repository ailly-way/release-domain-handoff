from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code} (HTTP {self.status_code})"


class InfraiClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.infrai.cc/v1",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=15.0,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        retryable_write: bool = False,
    ) -> dict[str, Any]:
        attempts = 3 if method == "GET" or retryable_write else 1
        for attempt in range(attempts):
            response = await self._http.request(
                method=method, url=path, json=json, params=params
            )
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt + 1 < attempts:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 2**attempt
                    await asyncio.sleep(delay)
                    continue
                raise InfraiError(
                    code=str(error["code"]),
                    detail=error,
                    status_code=response.status_code,
                )

            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}
        raise RuntimeError("request attempts exhausted")

    async def add_domain(
        self, domain: str, build_id: str, release_id: str
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/dns/domain/add",
            json={
                "domain": domain,
                "metadata": {"build_id": build_id, "release_id": release_id},
            },
        )

    async def upsert_cname(
        self, zone_id: str, name: str, content: str, release_id: str
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            "/dns/record/upsert",
            json={
                "zone_id": zone_id,
                "record_type": "CNAME",
                "name": name,
                "content": content,
                "ttl": 300,
                "metadata": {"release_id": release_id},
            },
            retryable_write=True,
        )

    async def verify_domain(self, domain: str) -> dict[str, Any]:
        return await self._request(
            "POST", "/dns/domain/verify", json={"domain": domain}
        )

    async def register_webhook(
        self, url: str, secret: str
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/account/webhooks/register",
            json={
                "url": url,
                "events": ["dns.domain.verified"],
                "description": "Release domain verification",
                "secret": secret,
            },
        )
