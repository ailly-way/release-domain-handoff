from __future__ import annotations

import hashlib
import hmac
import json
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any, AsyncIterator

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl

from .domain_service import DomainReleaseService
from .infrai_client import InfraiClient, InfraiError


class DomainOnboardingRequest(BaseModel):
    domain: str = Field(min_length=3)
    target: str = Field(min_length=3)
    build_id: str = Field(min_length=1)
    release_id: str = Field(min_length=1)


class WebhookRegistrationRequest(BaseModel):
    public_url: HttpUrl


class WebhookEvent(BaseModel):
    event: str
    data: dict[str, Any]


def valid_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    supplied = signature.removeprefix("sha256=")
    return hmac.compare_digest(expected, supplied)


def create_app(
    client: InfraiClient | None = None, webhook_secret: str | None = None
) -> FastAPI:
    owned_client = client is None
    if client is None:
        api_key = os.environ["INFRAI_API_KEY"]
        client = InfraiClient(api_key=api_key)
    secret = webhook_secret or os.environ["INFRAI_WEBHOOK_SECRET"]
    service = DomainReleaseService(client)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if owned_client:
            await client.close()

    app = FastAPI(title="Release domain handoff", lifespan=lifespan)

    @app.exception_handler(InfraiError)
    async def infrai_error_handler(_: Request, exc: InfraiError):
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        return JSONResponse(
            status_code=status,
            content={"detail": {"code": exc.code, "message": exc.detail.get("message")}},
        )

    @app.post("/release-domains", status_code=202)
    async def onboard_domain(request: DomainOnboardingRequest) -> dict[str, Any]:
        diagnostic = await service.onboard(
            request.domain, request.target, request.build_id, request.release_id
        )
        return asdict(diagnostic)

    @app.get("/release-domains/{domain}")
    async def release_diagnostic(domain: str) -> dict[str, Any]:
        diagnostic = service.get_diagnostic(domain)
        if diagnostic is None:
            raise HTTPException(status_code=404, detail="Domain release was not found")
        return asdict(diagnostic)

    @app.post("/webhook-registration")
    async def register_webhook(request: WebhookRegistrationRequest) -> dict[str, Any]:
        url = f"{str(request.public_url).rstrip('/')}/webhooks/infrai"
        return await client.register_webhook(url, secret)

    @app.post("/webhooks/infrai")
    async def receive_webhook(
        request: Request, x_webhook_signature: str = Header(alias="X-Webhook-Signature")
    ) -> dict[str, bool]:
        body = await request.body()
        if not valid_signature(body, x_webhook_signature, secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        event = WebhookEvent.model_validate(json.loads(body))
        if event.event == "dns.domain.verified":
            domain = str(event.data["domain"])
            service.mark_verified(domain)
        return {"accepted": True}

    return app
