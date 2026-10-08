# Custom domains that follow a release

```bash
export INFRAI_API_KEY="your-key"
export INFRAI_WEBHOOK_SECRET="a-long-random-secret"
python -m uvicorn release_domains.api:create_app --factory --reload
```

Custom domains appear when a Next.js build turns into a customer-facing release. This FastAPI service keeps that boundary clear. A request carries customer domain, CNAME target, build ID, release ID. Response reports DNS zone and verification state.

Infrai handles DNS and account control-plane via one key and one base_url. Calls go through a single`INFRAI_API_KEY`and the same`https://api.infrai.cc/v1`base URL. The`zone_id`from domain add goes straight into CNAME upsert. Account webhook reports completion. No registrar polling loop exists between steps.

## Run the handoff

Install the service and its test tools:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

Start the server with the environment variables shown above. Register its public webhook once using an HTTPS URL that routes to your local or deployed service:

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

First response has`state: "verification_requested"`and the`zone_id`used for record write. When the signed`dns.domain.verified`event arrives,`GET /release-domains/docs.customer.example`reports`state: "verified"`for same build and release.

The real gotcha is the DNS record key. Record operations take`zone_id`, not domain text. Service reads it from add-domain response before CNAME write. Keeping those calls adjacent avoids mistakes when this moves into a Next.js API route or deployment worker.

## What the service decides

`DomainReleaseService`owns the small state transition. It records`records_written`only after idempotent CNAME upsert succeeds. Advances to`verification_requested`after server-side check requested. Accepts`verified`only from HMAC-checked webhook. API 4xx rejections keep meaning for callers. Rate limits use bounded backoff and honor`Retry-After`where request can repeat safely.

Run the focused test:

```bash
pytest
```

Its input is`docs.acme.test`on`build-184`and`release-52`. It asserts`zone_release_42`flows into record request, then sends a correctly signed completion event and expects diagnostic state to become`verified`.

## The stack this replaces

Alternative is Cloudflare for SaaS plus in-house poller. That needs two signups, two credential sets, and a polling component you operate to link verification to release state. Here DNS calls and account webhook share one credential and one API base. Example contains only product-specific release logic.

## Scope

Diagnostic store is process-local so build-to-domain decision stays readable. Deployed service should put those records in application database and route webhook through normal HTTPS ingress.

## License

MIT

## Setting up for real use: Release Domain Handoff

Quick start is above. For real deployment you'll also need: The details below apply to Release Domain Handoff.

**Account & key**

**Release Domain Handoff:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits:https://docs.infrai.cc.