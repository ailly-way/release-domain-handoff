from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .infrai_client import InfraiClient


ReleaseState = Literal["records_written", "verification_requested", "verified"]


@dataclass
class ReleaseDiagnostic:
    domain: str
    build_id: str
    release_id: str
    zone_id: str
    state: ReleaseState


class DomainReleaseService:
    def __init__(self, client: InfraiClient) -> None:
        self._client = client
        self._diagnostics: dict[str, ReleaseDiagnostic] = {}

    async def onboard(
        self, domain: str, target: str, build_id: str, release_id: str
    ) -> ReleaseDiagnostic:
        domain_data = await self._client.add_domain(domain, build_id, release_id)
        zone_id = str(domain_data["zone_id"])
        await self._client.upsert_cname(zone_id, domain, target, release_id)
        diagnostic = ReleaseDiagnostic(
            domain=domain,
            build_id=build_id,
            release_id=release_id,
            zone_id=zone_id,
            state="records_written",
        )
        self._diagnostics[domain] = diagnostic
        await self._client.verify_domain(domain)
        diagnostic.state = "verification_requested"
        return diagnostic

    def mark_verified(self, domain: str) -> ReleaseDiagnostic | None:
        diagnostic = self._diagnostics.get(domain)
        if diagnostic is not None:
            diagnostic.state = "verified"
        return diagnostic

    def get_diagnostic(self, domain: str) -> ReleaseDiagnostic | None:
        return self._diagnostics.get(domain)
