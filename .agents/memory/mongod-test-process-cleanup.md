---
name: Local mongod for tests dies between tool calls
description: Why throwaway-Mongo backend tests must launch mongod inside the same bash command that runs pytest
---

Backend tests that need real Mongo (no mongomock installed) can't rely on a
mongod started in a *previous* bash tool call — the Replit bash tool tears down
the command's process group on return, so even `--fork`/`setsid`/`nohup &`
daemons are gone by the next call (port 27017 → connection refused).

**Rule:** start mongod AND run pytest in ONE bash command, then shut it down:
`mongod --dbpath /tmp/x --port 27017 --fork --logpath ... ` (NO pipe — piping
the forked output through `tail` hangs the tool), wait for a pymongo ping loop,
run `MONGO_URL=... pytest ...`, then `mongod --dbpath /tmp/x --shutdown`.

**Why:** verified Task #398 migration-framework tests; tests skip (not fail)
when Mongo is unreachable, so a dead daemon silently turns a green suite into
all-skipped. Always confirm with `-rs` that they actually ran.
