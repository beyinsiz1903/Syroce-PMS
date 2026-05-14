# Threat Model

## Project Overview

Syroce PMS is a multi-tenant hotel property-management system with a React/Vite frontend and a FastAPI backend backed by MongoDB, Redis, and Celery. The system serves hotel staff, property administrators, agency/B2B integrations, guest/mobile-app users, and third-party channel/webhook providers. In production, the main security objective is preserving strict tenant isolation while protecting guest PII, hotel operational data, payment-adjacent records, credentials, API keys, and integration secrets.

This threat model is production-scoped. Test suites, e2e harnesses, stress fixtures, sandbox simulations, and mockup-only code are out of scope unless a concrete production path reaches them. Replit deployment TLS is assumed to be handled by the platform.

## Assets

- **User accounts and sessions** — JWT access tokens, refresh tokens, 2FA state, guest/mobile sessions, B2B API keys, and webhook credentials. Compromise allows impersonation or long-lived access.
- **Tenant-scoped PMS data** — reservations, folios, room state, operational tasks, analytics, and rate/channel data. Cross-tenant disclosure or modification would be a severe business breach.
- **Guest PII and regulated identity data** — names, e-mail addresses, phone numbers, national/passport identifiers, online check-in submissions, review invites, QR charge state, and ID-photo metadata. Some flows also handle encrypted ID-photo blobs and compliance-sensitive audit trails.
- **Financial and payment-adjacent records** — folio charges, refunds/voids, cashier actions, and guest purchase/upsell records. Tampering can cause direct monetary loss.
- **Application and integration secrets** — `JWT_SECRET`, setup secrets, provider/admin tokens, Quick-ID credentials, webhook secrets, and outbound integration credentials. Leakage can enable privileged access to internal or third-party systems.
- **Availability-critical workflows** — public auth endpoints, webhook ingestion, guest flows, and operational APIs that drive front-desk and channel-management behavior. Abuse can disrupt hotel operations.

## Trust Boundaries

- **Client / server boundary** — browsers, mobile apps, guest devices, agency clients, and webhook senders all cross into the FastAPI API. The server must treat every request as untrusted.
- **Public / authenticated / privileged boundary** — the codebase mixes public routes, guest-authenticated flows, staff-authenticated routes, and setup/debug routes. Every boundary must be enforced server-side.
- **Tenant boundary** — the most important boundary in this system. Requests authenticated for one hotel must never expose or mutate another tenant’s data.
- **Server / database boundary** — FastAPI handlers and services query MongoDB directly. Missing filters or unsafe resolver/query patterns can immediately become cross-tenant disclosure or tampering.
- **Server / external service boundary** — channel managers, Quick-ID, e-mail, and other outbound integrations receive privileged server-side calls. These paths must resist SSRF, spoofed callbacks, and credential leakage.
- **Public static content boundary** — `/api/uploads` is publicly served and therefore must contain only content intended for public delivery. Sensitive uploads must live outside that mount.

## Scan Anchors

- Production entry points: `backend/server.py`, `backend/app.py`, router mounting/bootstrap code under `backend/bootstrap/`.
- Highest-risk areas: `backend/core/security.py`, `backend/routers/auth.py`, `backend/graphql_api/`, `backend/domains/guest/`, `backend/routers/b2b_api/`, channel/webhook providers under `backend/domains/channel_manager/providers/`.
- Public surfaces: `/api/auth/*`, public guest/review flows, webhooks, `/api/graphql`, `/api/docs`, `/api/openapi.json`, and `/api/uploads`.
- Usually ignore unless production reachability is shown: `backend/tests/`, `frontend/e2e-*`, sandbox simulation code, docs-only material, and local/dev helpers.

## Threat Categories

### Spoofing

This application accepts identity from JWTs, guest/mobile accounts, B2B API keys, and third-party webhooks. The system must validate bearer tokens on every protected route, distinguish access tokens from refresh tokens, enforce revocation/invalid-before semantics, and verify any webhook or API-key caller before trusting tenant or booking identifiers. Setup/debug paths must remain fail-closed in production and must never rely on hardcoded fallback secrets.

### Tampering

The backend exposes operational and financial actions across many routers, including guest purchases, folio updates, room changes, channel updates, and online check-in state. All business-critical operations must derive authorization and tenant scope from trusted server-side identity, not client input. Public token-based flows must bind the token to the intended tenant/resource and reject replay or reuse where single-use semantics are expected.

### Information Disclosure

The dominant disclosure risk is cross-tenant exposure from missing `tenant_id` filters or unauthenticated routes that directly query MongoDB. Guest PII, booking data, room/occupancy data, financial records, API-key metadata, and identity-check artifacts must only be returned to the owning tenant and authorized role. Publicly served uploads must exclude sensitive content, and error/debug/documentation surfaces must not leak internal data that materially helps an attacker.

### Denial of Service

Public auth, guest, and webhook endpoints can be abused to create operational load against hotels and central infrastructure. Unauthenticated or low-auth surfaces must impose size limits, validation, and rate-limiting appropriate to their cost. Expensive queries, public scraping surfaces, and provider callback handlers must fail safely under abuse without cascading into tenant-wide outages.

### Elevation of Privilege

Privilege escalation in this codebase can occur through missing route guards, broken role checks, cross-tenant IDORs, or unauthenticated access to data-rich endpoints. Staff-only, admin-only, guest-only, and B2B-only functions must each be enforced server-side. Any endpoint or resolver that reaches sensitive collections without authentication and tenant scoping should be treated as a likely critical finding because it collapses both the public/authenticated and tenant-isolation boundaries at once.
