---
name: Sentry before_send noise filtering for expected ERROR logs
description: Why benign/expected ERROR-level logs page Sentry and the standard way to silence them without losing real incidents.
---

Sentry's default logging integration captures every ERROR-level log record as an
event. So any *expected* or *benign* condition that some library logs at ERROR
(e.g. an enforced security policy denial) will page the on-call channel even
though nothing is wrong.

**Rule:** when a new expected ERROR-class shows up as Sentry alert noise, add a
narrow predicate to the `before_send` hook that drops ONLY that class, plus a
cumulative drop counter exposed via the filter-stats accessor for ops visibility.
Do NOT silence by lowering the source log level (loses console visibility) and do
NOT drop on a broad substring (can hide real incidents).

**Why:** the project already standardized this pattern for restart-bind noise and
non-prod sustained-transient-DB noise; introspection-disabled denials were the
third case. Matching must anchor on the library's FULL message template (regex,
`re.search` to tolerate logger prefixes), never a bare phrase, so a genuine error
that merely mentions the phrase still pages.

**How to apply:** predicate runs first in `before_send`, returns True → event
dropped + counter++ + INFO log line; everything else flows through PII scrub.
Add positive (template, prefixed) and negative (near-miss phrase, unrelated
error) tests. Drop unconditionally across envs only when the class is NEVER an
actionable server fault (a client-side policy denial qualifies; a sustained DB
outage does not — that one must still page in prod/pilot).
