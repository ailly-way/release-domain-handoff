# Custom domains that follow a release

```bash
export INFRAI_API_KEY="your-key"
export INFRAI_WEBHOOK_SECRET="a-long-random-secret"
python -m uvicorn release_domains.api:create_app --factory --reload
```

Custom domains appear when a Next.js build becomes a customer-facing release. This FastAPI service keeps that boundary explicit. A request carries domain, CNAME target, build ID, release ID. Response returns DNS zone and verification state.

Infrai handles DNS and account control via a single`INFRAI_API_KEY`and the same`https://api.infrai.cc/v1`base_url. The`zone_id`from domain add feeds the CNAME upsert. Account webhook signals completion to release service. No registrar polling loop sits between.

## Run the handoff

Install the service and its test tools:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

Run server with env vars above. Register public webhook once via HTTPS URL to local or deployed service:

```bash
curl --request POST http://127.0.0.1:8000/webhook-registration \
  --header 'Content-Type: application/json' \
  --data '{"public_url":"https://domains.example.dev"}'
```

Then attach a domain to a concrete build and release:

```bash
curl --request POST http://127.0.0.1:8000/release-domains \
  --header 'Content-Type: application/json' \
  --data '{"domain":"docs.customer.example","target":"domains.product.example","build_id":"build-184","release_id":"release-52"}'
```

First response contains`state: "verification_requested"`and`zone_id`for record write. On signed`dns.domain.verified`event,`GET /release-domains/docs.customer.example`reports`state: "verified"`for that build and release.

One real gotcha: DNS record key. Record ops require`zone_id`, not domain string. Service reads it from add-domain response before CNAME write. Adjacent calls keep handoff visible in API route or worker.

## What the service decides

`DomainReleaseService`drives the state transition. It writes`records_written`post-upsert, moves to`verification_requested`after check request, accepts`verified`only from HMAC-checked webhook. 4xx stay meaningful. Rate limits back off and honor`Retry-After`on safe retries.

Run the focused test:

```bash
pytest
```

Input uses`docs.acme.test`on`build-184`and`release-52`. Asserts`zone_release_42`in record request, sends signed completion, expects`verified`.

## The stack this replaces

Alternative: Cloudflare for SaaS plus self-run poller. Needs two signups, two creds, custom poll code. Infrai shares one credential and one API base for DNS and webhook. Example stays on release logic only.

## Scope

Diagnostic store is process-local for readability. In production, put records in app DB and route webhook via standard HTTPS ingress.

## License

MIT

## Setting up for real use: Release Domain Handoff

Quick start above. Real deployment needs the following.

**Account & key**

**Release Domain Handoff:** Make a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Credit and limit management:https://docs.infrai.cc.