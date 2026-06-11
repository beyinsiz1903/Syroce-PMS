---
name: Agent cannot run git; GitHub sync is operator-only
description: The agent environment hard-blocks all git (even fetch). Resolving a GitHub origin divergence (ahead/behind, conflicted Pull) must be done by the operator in Replit Shell + Git pane, never by the agent.
---

The agent (main agent and main-agent-executed project tasks) **cannot run any git
command** in this repl — not even read/`fetch`. Attempts return:
`Destructive git operations are not allowed in the main agent` (e.g. on
`.git/objects/maintenance.lock`). So the agent cannot fetch, merge, resolve
conflicts against `origin/main`, commit, or push.

**Consequence:** a GitHub divergence (Sync pane shows N incoming / M outgoing, every
Pull starts a conflicted merge) **must be resolved by the operator**, not the agent.
The agent's only role is to hand the operator an exact, safe command sequence and
interpret the output.

**Why:** the agent has no GitHub-authenticated path and git is sandboxed away. Even a
background project task assigned to the main agent runs in the main env with git
blocked.

**How to apply (this two-repl repo):** when the operator reports a conflicted Pull /
N-incoming-M-outgoing on THIS mobile/static repl:
- Give them a Replit **Shell** script that: clears `.git/index.lock` + `git merge
  --abort`; `git fetch origin main`; `git merge --no-commit --no-ff origin/main`;
  resolves generated `frontend/build/*` by **taking origin's** version
  (`git checkout --theirs -- frontend/build`) — origin/the VM repl owns that build, and
  since we keep origin's source wholesale the build is already consistent, so **no
  rebuild is needed**; force-keeps THIS repl's files with `git checkout HEAD --
  .replit .agents/memory/deploy-build-wrong-artifact.md`; **stops** if any other
  conflicted file remains (`git diff --name-only --diff-filter=U`) and asks the
  operator to paste the list; then `git commit`.
- Have the operator **Push via the Git pane** (handles GitHub auth), not `git push`
  from Shell (may lack the credential).
- `.replit` is shared in git but each repl wants its own deployment block, so it
  flip-flops every sync — always re-assert THIS repl's static/mobile `.replit` (keep
  ours) after a sync, then have the operator **republish** the static mobile deploy.
