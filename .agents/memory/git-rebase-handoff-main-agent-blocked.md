---
name: Main-agent git lockdown blocks in-tree rebase completion
description: Why a stuck in-tree interactive rebase can only be finished by the user in Shell, not the agent or an isolated task agent
---

The main agent's git block is operation/path based, not just `git commit`/`git rebase`: `git add`, `git rebase --continue/--abort`, AND even `rm .git/index.lock` are all rejected with "Destructive git operations are not allowed in the main agent." (A blocked `git add` still leaves a stale `.git/index.lock`, sized like a real partial index.)

**Why:** the platform guards repo-mutating actions to prevent corruption; the guard also catches filesystem writes to `.git/index.lock`.

**How to apply** when an interactive rebase is stopped on a conflict in the MAIN working tree:
- You CAN: edit the conflicted file to resolve it and verify OFFLINE (py_compile, `node --check`, targeted pytest). Do that first — it removes the crash-on-restart risk and proves the resolution before any handoff.
- You CANNOT: stage it, continue/abort the rebase, or clear a stale `.git/index.lock`.
- An isolated Project Task agent CANNOT finish it either — task agents run in separate Repls; `.git/rebase-merge/` state and `index.lock` live only in the main tree and are invisible there.
- So hand the USER the exact Shell sequence. Because the blocked `git add` left a stale lock, the user must remove it FIRST:
  - Continue: `rm -f .git/index.lock` -> `git add <resolved-file>` -> `git rebase --continue` -> `git push` (fast-forward when local = origin-tip + replayed commits, no force).
  - Abort: `rm -f .git/index.lock` -> `git rebase --abort`.
- A duplicate-fix conflict (same SPA-429 static-asset rate-limit exemption done on two screens) is benign: keep the more conservative version if it satisfies BOTH sides' test files; prove it with both test files green.
