# OriginSync AI

OriginSync is a cross-border trade compliance and escrow settlement service. The
repository is a monorepo with a FastAPI API, a Next.js telemetry dashboard, and
Supabase database migrations.

## Components

- `supabase/migrations/`: PostgreSQL schema, organization-scoped RLS, RoO rules,
  audit records, and pgvector semantic-cache indexes/functions.
- `backend/`: asynchronous API, Vertex AI classification, fail-closed rules of
  origin checks, RIGS scoring, HMAC-verified webhooks, and PayPal payouts.
- `frontend/`: offline-tolerant telemetry control room.
- `gateway/`: optional Caddy ingress for Cloud Run deployments.
- `render.yaml`: Render blueprint for the API and control room. The database is
  hosted separately in Supabase.

## Configuration

See the environment variables in `render.yaml`. The API requires a Supabase
PostgreSQL connection string, Supabase URL and anon key, a Vertex project and
service-account JSON (or an available Google Application Default Credential),
and PayPal credentials for settlement. Set `PAYPAL_ENVIRONMENT=sandbox` while
testing. Webhook HMAC secrets are independent and required for their respective
webhook routes. `SUPABASE_SERVICE_ROLE_KEY` is only used by the backend for
private document uploads and must never be exposed to the browser. Never use
sample secrets in deployed environments.

The frontend requires `NEXT_PUBLIC_API_BASE_URL` to be the externally reachable
HTTPS base URL of the API. In Render, set it explicitly to the API URL so it is
available during Next.js build as well as at runtime.

## Local development

Apply the SQL migration to a Supabase project, set backend configuration, then:

```sh
cd backend
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

The dashboard can be run with:

```sh
cd frontend
npm ci
npm run dev
```

Protected API routes require a valid Supabase access token and an organization
membership. Settlement is only attempted after a matching active RoO rule
verifies preferential origin and all RIGS evidence is available above the
configured threshold. Growth and stakeholder signals are calculated from
historical settled trades; insufficient history, missing invoice evidence, and
ambiguous authoritative rules fail closed and require review. The PayPal and
n8n webhook endpoints require an upstream signer to provide
`X-OriginSync-Timestamp` and `X-OriginSync-Signature` (`sha256=<hex>`), where the
signature is HMAC-SHA256 of `<timestamp>.<raw request body>`. PayPal does not
provide this shared-secret signature natively; configure a trusted webhook
adapter to verify PayPal's transmission signature and apply the OriginSync HMAC.
Load only currently effective, source-linked tariff rules into `tariff_rules`;
each rule requires a verified source URL, source version, SHA-256 source digest,
and reviewer identity. RIGS uses risk (0.35), invoice intent alignment (0.25),
historical organization growth (0.15), and historical beneficiary settlement
success (0.25). Growth and stakeholder components remain unavailable until the
required history exists; unavailable evidence prevents automated settlement
rather than receiving a neutral score. Growth requires at least three settled
trades in each of the recent and prior 90-day windows; stakeholder trust
requires at least three prior payouts for the beneficiary.
Payouts additionally require an administrator-verified beneficiary in
`trusted_beneficiaries`; authenticated clients have read-only access to trade
records and cannot manufacture settlement history.

The frontend uses patched Next.js 16.3.8 rather than the initially requested
Next.js 14 line because the dependency audit identified critical/high advisories
with no safe fix in that release line. The App Router, TypeScript, Tailwind, and
AG Grid Community control-room architecture is unchanged.

## Container deployment

Build the backend with `docker build -t originsync-api ./backend` and the
frontend with `docker build -t originsync-control-room ./frontend`, passing
`NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, and
`NEXT_PUBLIC_SUPABASE_ANON_KEY` as frontend build arguments. Provide backend
secrets as runtime environment variables, not image build arguments. For Cloud
Run, deploy the API on port 8080 and the Next.js standalone image on port 3000;
the optional Caddy image in `gateway/` routes API paths to `API_UPSTREAM` and
all other paths to `FRONTEND_UPSTREAM`. Configure Cloud Run minimum instances,
concurrency, Secret Manager bindings, and service URLs for the target
availability objectives. Render uses the native services in `render.yaml`.

FastAPI publishes the OpenAPI 3.1 document at `/openapi.json` for APIMatic
client generation.
