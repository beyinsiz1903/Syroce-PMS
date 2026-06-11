---
name: Explore subagent is unreliable for line-level security audits
description: When auditing many write sites for a security gap, the explore subagent hallucinates line/function/field mappings; verify each claim before reporting or acting.
---

# Explore subagent unreliable for line-level security audits

When you dispatch the explore subagent to audit "which call sites do/don't do X"
across many files (e.g. which `db.guests.*` writes skip PII encryption), treat its
per-site table as **leads, not facts**.

**Observed failure mode:** asked to map every guest-write site to (encrypts?
which PII fields?), it returned a confident table where multiple "most severe"
rows were wrong: it attributed `id_number`/`date_of_birth` writes to functions
that only `$set` `tags`/`vip_status`/`loyalty_points`, and it flagged a site as
unencrypted that in fact called `encrypt_document` a few lines above the insert.
Roughly 3 of 4 spot-checked high-severity claims were false. The line numbers it
cited often pointed at an unrelated function.

**Why:** the explorer summarizes; it does not reliably bind a claimed field to the
exact dict literal at the cited line, and it can miss an encryption call that is a
few lines away from the write call.

**How to apply:** use explore to *enumerate candidate* sites fast, then open each
candidate yourself (read the dict literal at the write + a few lines above for an
encrypt call) before you (a) report a vulnerability count to the operator or
(b) edit anything. Never forward an explore security table to the user as a
finding without per-claim verification — doing so risks a fake finding (false
alarm), which violates the no-fake doctrine just as much as a fake-green.
