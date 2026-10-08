import hashlib
import hmac
import json
from typing import Any

import httpx
from fastapi.testclient import TestClient

from release_domains.api import create_app
from release_domains.infrai_client import InfraiClient


def test_zone_id_flows_to_record_and_signed_event_completes_release() -> None:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append({"method": request.method, "path": request.url.path, "body": body})
        if request.url.path.endswith("/dns/domain/add"):
            data = {"zone_id": "zone_release_42"}
        else:
            data = {"accepted": True}
        return httpx.Response(200, json={"ok": True, "data": data, "error": None})

    infrai = InfraiClient(
        api_key="test-key", transport=httpx.MockTransport(handler)
    )
    app = create_app(client=infrai, webhook_secret="local-secret")

    with TestClient(app) as browser:
        started = browser.post(
            "/release-domains",
            json={
                "domain": "docs.acme.test",
                "target": "domains.product.test",
                "build_id": "build-184",
                "release_id": "release-52",
            },
        )
        assert started.status_code == 202
        assert started.json()["state"] == "verification_requested"
        assert calls[1]["body"]["zone_id"] == "zone_release_42"

        payload = json.dumps(
            {"event": "dns.domain.verified", "data": {"domain": "docs.acme.test"}},
            separators=(",", ":"),
        ).encode()
        signature = hmac.new(b"local-secret", payload, hashlib.sha256).hexdigest()
        delivered = browser.post(
            "/webhooks/infrai",
            content=payload,
            headers={"X-Webhook-Signature": f"sha256={signature}"},
        )
        assert delivered.status_code == 200
        assert browser.get("/release-domains/docs.acme.test").json()["state"] == "verified"
