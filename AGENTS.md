# AGENTS.md — Operating Rules for AI Agents

> **Read `PROGRESS.md` first** to find where you left off.

## Quick Reference

### Session Start
1. Confirm `docs/SPEC.md` and `IMPLEMENTATION_PLAN.md` exist.
2. Read `PROGRESS.md`. Run `git status`, `git branch --show-current`, `git log --oneline -15`.
3. Find the first non-DONE step. Read only that step and referenced spec sections.
4. If the tree is dirty with `wip:` commits, inspect, test, and fix before starting new work.

### Session End (also when quota is low)
1. Update `PROGRESS.md` with current status, next action, and blockers.
2. `git add -A && git commit -m "wip(<scope>): <what>"` and `git push`.

### Step Loop
1. **Plan**: restate goal in `PROGRESS.md`.
2. **Write tests first or alongside** the code.
3. **Implement** the smallest satisfying change.
4. **Run the gate** (see below).
5. **Update docs** touched by the change.
6. **Update `PROGRESS.md`**, mark step DONE.
7. **Commit** (Conventional Commits) and **push**.

### Test Gates
| Gate | Command | Runs |
|---|---|---|
| **Quick** | `python scripts/make.py check` | ruff + format + mypy + unit tests |
| **Full** | `python scripts/make.py test-all` | Quick + agent + integration |
| **Stack** | `python scripts/make.py smoke` | Docker Compose up, /health, demo query, tear down |
| **Frontend** | `python scripts/make.py fe-check` | eslint + tsc + vitest + build |

### Commit Conventions
`type(scope): summary [step-id]`
Types: `feat, fix, test, docs, refactor, chore, ci, perf, build, wip`

### Git Workflow
- `main` is always green. Never commit directly after S0.3.
- One branch per stage: `stage/<N>-<slug>`.
- Commit after every step; push after every commit.
- Stage exit: PR → green CI → merge → tag `stage-N-complete`.

### Debugging Discipline
- Max 3 attempts with same approach. Then try a different approach (max 2 more) or ask the human.
- Read the actual error before editing. Don't shotgun changes.

### Absolute Prohibitions
- No destructive commands outside the repo.
- No modifying global machine config without telling the human.
- No installing system software without telling the human.
- No invented numbers — every metric from a committed report.
- No features outside Must/Should until all are done.
- No credentials in state, prompts, traces, logs, API responses, or test snapshots.
- No running held-out test split except at S5.5 snapshot and S9.5 final.

### When to Stop and Ask the Human
Only for: installing system software, GitHub auth, API keys/secrets, product options not covered in the plan, spending real money, making repo public, or blocker after 3-attempt rule.

## Key Design Rules (each has a test)
1. `ValidatedSQL` only constructible by the validator. Executor accepts only `ValidatedSQL`.
2. Only `app/tools/execution.py` and `app/tools/introspection.py` connect to target DBs.
3. Credentials decrypted only in those two modules; never serialized/logged.
4. Every app-DB query on user data takes `user_id` as required parameter.
5. Graph state: only IDs and small serializable data.

## Windows Note
This project runs on native Windows with PowerShell. Use `python scripts/make.py <target>` instead of `make <target>`.
