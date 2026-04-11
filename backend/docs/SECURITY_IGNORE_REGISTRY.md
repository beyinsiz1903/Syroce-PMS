# Security Vulnerability Ignore Registry

All `--ignore-vuln` entries in `.github/workflows/ci-cd.yml` MUST be documented here.
Any new ignore MUST include: reason, expiry, owner, and remediation plan.

---

## Active Ignores

| CVE / ID | Package | Version | Reason | Added | Expiry | Owner | Remediation |
|---|---|---|---|---|---|---|---|
| PYSEC-2024-62920 | (transitive) | — | Low-risk transitive dependency, no direct exposure | 2026-03 | 2026-06 | Backend team | Monitor upstream fix |
| PYSEC-2024-113 | (transitive) | — | Low-risk transitive dependency, no direct exposure | 2026-03 | 2026-06 | Backend team | Monitor upstream fix |
| CVE-2024-23342 | ecdsa | 0.19.1 | Minerva timing attack on P-256. We don't use ecdsa for signing. Project considers side-channel OOS. | 2026-03 | 2026-09 | Backend team | Replace ecdsa if used directly, or wait for upstream |
| GHSA-rf74-v2fm-23pw | nltk | 3.9.3 | JSONTaggedDecoder recursion DoS. We don't pass external JSON to JSONTaggedDecoder. | 2026-03 | 2026-06 | Backend team | Upgrade nltk when fix released |
| CVE-2026-33230 | nltk | 3.9.3 | Reflected XSS in WordNet Browser. We don't use nltk.app.wordnet_app. | 2026-03 | 2026-06 | Backend team | Upgrade nltk when fix released |
| CVE-2026-33231 | nltk | 3.9.3 | Unauthenticated shutdown of WordNet Browser. We don't use nltk.app.wordnet_app. | 2026-03 | 2026-06 | Backend team | Upgrade nltk when fix released |
| CVE-2026-4539 | pygments | 2.19.2 | ReDoS in AdlLexer (archetype.py). Local access only. We don't process untrusted ADL input. | 2026-03 | 2026-06 | Backend team | Upgrade pygments when fix released |

## Review Process

1. **Quarterly audit**: Review all entries above. Remove any that have been fixed upstream.
2. **New ignore**: Must be approved in PR review with justification.
3. **Expired ignore**: If past expiry and no remediation, escalate to security lead.
