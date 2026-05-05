# EAS → GitHub Actions webhook relay

Tiny stateless HTTP service that converts an Expo EAS **BUILD** webhook into a
GitHub Actions `repository_dispatch` (event type `eas-build-finished`) so that
[`.github/workflows/mobile-smoke.yml`](../../.github/workflows/mobile-smoke.yml)
runs automatically the moment an EAS build finishes — no operator has to
remember to click "Run workflow".

```
EAS build webhook  ──HMAC-SHA1──▶  this relay  ──Bearer token──▶  GitHub API
                                                                  POST /repos/<owner>/<repo>/dispatches
```

## Wire format

The relay implements the contract documented in
[`mobile/README.md` → "Otomatik smoke CI hook'u"](../../mobile/README.md#otomatik-smoke-ci-hooku).

- Inbound: `POST /eas` with the raw EAS webhook JSON body and an
  `expo-signature: sha1=<hex>` header.
- Outbound:
  ```
  POST https://api.github.com/repos/<owner>/<repo>/dispatches
  Authorization: Bearer <GITHUB_TOKEN>
  Accept:        application/vnd.github+json
  X-GitHub-Api-Version: 2022-11-28

  {
    "event_type": "eas-build-finished",
    "client_payload": {
      "platform":     "ios" | "android",
      "build_url":    "<artifacts.applicationArchiveUrl>",
      "build_id":     "<id>",
      "profile":      "preview" | "production",
      "issue_number": "<optional, parsed from commit/branch>"
    }
  }
  ```

The relay **swallows** any webhook whose `status` is not `finished` (e.g.
`in-queue`, `in-progress`, `errored`, `canceled`) so failed builds don't kick
off a smoke run.

`issue_number` is best-effort: it's extracted from
`metadata.gitCommitMessage`, `metadata.message`, or `metadata.gitBranch` if any
of them contains a `PR-<n>`, `#<n>`, or `pr-<n>/...` token. If nothing is
found, the field is omitted and the workflow simply skips PR commenting.

## Configuration

All configuration is read from environment variables:

| Variable                  | Required | Description                                                    |
| ------------------------- | -------- | -------------------------------------------------------------- |
| `EAS_WEBHOOK_SECRET`      | yes      | Shared secret returned by `eas webhook:create`. Used to verify HMAC. |
| `GITHUB_TOKEN`            | yes      | PAT or GitHub App installation token with `repo` scope.        |
| `GITHUB_REPO`             | yes      | Target repo in `owner/repo` format (e.g. `syroce/pms`).        |
| `GITHUB_DEFAULT_PROFILE`  | no       | Fallback profile when the EAS payload omits one. Default `preview`. |
| `WEBHOOK_PATH`            | no       | HTTP path the webhook is served on. Default `/eas`.            |
| `PORT`                    | no       | TCP port. Default `8080`.                                      |
| `MAX_BODY_BYTES`          | no       | Request body size cap. Default `1048576` (1 MiB).              |
| `RELAY_USER_AGENT`        | no       | `User-Agent` header sent to GitHub. Default `eas-webhook-relay`. |

## Running

```bash
cd infra/eas-webhook-relay

# tests (no dependencies — uses node:test + node:assert)
node --test test

# local dev
EAS_WEBHOOK_SECRET=dev-secret \
GITHUB_TOKEN=ghp_xxx \
GITHUB_REPO=syroce/pms \
node src/server.js
```

The service has zero runtime dependencies. The only npm metadata in
`package.json` is for tooling consistency — `npm install` is a no-op.

### Container

```bash
docker build -t eas-webhook-relay:local .
docker run --rm -p 8080:8080 \
  -e EAS_WEBHOOK_SECRET=dev-secret \
  -e GITHUB_TOKEN=ghp_xxx \
  -e GITHUB_REPO=syroce/pms \
  eas-webhook-relay:local
```

### Kubernetes

`k8s/deployment.yml` is templated the same way as the rest of `infra/k8s/`
(`${REGISTRY}` / `${IMAGE_TAG}` / secret env interpolation). It exposes the
relay at `https://eas-relay.syroce.com/eas` via the existing nginx-ingress +
cert-manager stack.

Required deploy-time secrets:

```
EAS_WEBHOOK_SECRET           # same value passed to `eas webhook:create`
EAS_RELAY_GITHUB_TOKEN       # PAT with repo scope (or GitHub App installation token)
EAS_RELAY_GITHUB_REPO        # e.g. syroce/pms
```

### Cloud Function / Lambda

`src/handler.js` exports `handleWebhook({ rawBody, headers, config })` so the
same code works as a serverless handler — wrap it in your platform's adapter
(API Gateway proxy, Cloudflare Worker, GCP HTTP function, etc.) and pass the
raw request body through unchanged. Do **not** parse/re-stringify JSON before
passing it in: the HMAC is over the exact bytes EAS sent.

## Wiring up the EAS webhook

```bash
# pick a strong secret first
export EAS_WEBHOOK_SECRET=$(openssl rand -hex 32)

# register the webhook (returns a confirmation; the secret you pass is the one
# the relay verifies against)
eas webhook:create \
  --event BUILD \
  --url https://eas-relay.syroce.com/eas \
  --secret "$EAS_WEBHOOK_SECRET"

# list / verify
eas webhook:list

# rotate
eas webhook:update --id <id> --secret "$NEW_SECRET"
# then update EAS_WEBHOOK_SECRET in the relay's runtime env
```

## Operations runbook

### Healthcheck

```
GET /health   → 200 {"ok":true}
```

### "A build finished but smoke didn't run"

1. EAS dashboard → the build → **Webhooks** tab → confirm the delivery
   succeeded (HTTP 202 from the relay). HTTP 401 = bad/missing signature, 502
   = GitHub API rejected the dispatch.
2. Relay logs (`kubectl logs -n syroce deploy/eas-webhook-relay`) — look for:
   - `[eas-relay] dispatched eas-build-finished` (success path)
   - `[eas-relay] swallowing non-finished webhook` (build still in progress
     or errored — expected)
   - `[eas-relay] rejected …` (4xx — caller error, signature/profile/etc.)
   - `[eas-relay] error …` (5xx — GitHub API down or token expired)
3. GitHub → repo → **Actions** → filter `event:repository_dispatch` to confirm
   the run was queued. If it wasn't, the GitHub token most likely lost `repo`
   scope.

### Manual replay

If a webhook delivery was lost (relay was down, GitHub was down, etc.), you
can fall back to the manual `workflow_dispatch` trigger documented in
`mobile/README.md` — paste the EAS artifact URL into the Actions UI.

### Token rotation

1. Mint a new PAT / GitHub App token with `repo` scope.
2. Update the `eas-webhook-relay-secrets` Secret (or your serverless platform's
   env vars).
3. Restart the deployment: `kubectl rollout restart -n syroce deploy/eas-webhook-relay`.
4. Send a test dispatch from the EAS dashboard ("Resend" on the latest
   delivery) and verify a green `Mobile Smoke (post EAS build)` run appears.

### Secret rotation

Same flow with `EAS_WEBHOOK_SECRET` — but you must update the EAS side
(`eas webhook:update`) **and** the relay env at the same time. Brief downtime
of webhook delivery is acceptable; the relay simply 401s during the
mismatch window.
