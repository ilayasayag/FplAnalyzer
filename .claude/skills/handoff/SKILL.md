---
name: handoff
description: Generate an elaborate, end-to-end project handoff document so another agent (or a future session) can pick the project up cold. Captures EXACT status across missions/sprints, PRs, merges, deployments, branches, worktrees, validations, and per-area status — plus what changed since the previous handoff. Use when the user says "write/create a handoff", "hand this off", "summarize handoff end to end", or is about to hand the project to another agent.
---

# Handoff — write an elaborate end-to-end status document

Your job: produce a handoff so complete that a brand-new agent with **zero prior context** can read it and know exactly where the project stands and what to do next. Bias toward over-explaining. A handoff that is too short is the failure mode.

## Step 1 — Read the previous handoff (for "what came before")

Find the most recent prior handoff and read it fully:
```bash
ls -t *HANDOFF*.md **/*HANDOFF*.md 2>/dev/null
```
- If one exists, read it. Your new handoff must include a **"What happened since the last handoff"** section that diffs old → now. Preserve still-accurate architecture/gotchas (re-validate them, don't blindly copy).
- If none exists, reconstruct the "before" narrative from **this conversation** and from `git log`.
- Also read the project auto-memory if present: `~/.claude/projects/<slug>/memory/MEMORY.md` and any `project_*.md`.

## Step 2 — Gather LIVE ground truth (don't trust memory; verify)

Run these read-only checks and base the doc on their actual output:

```bash
# Branch / commits / push state
git status -sb
git rev-parse --abbrev-ref HEAD
git log --oneline -15
# Ahead/behind the upstream
git rev-list --left-right --count @{u}...HEAD 2>/dev/null
# Merge status: commits on this branch NOT in main
git log --oneline main..HEAD 2>/dev/null | wc -l
git log --oneline main..HEAD 2>/dev/null | head -30
# Uncommitted work (CRITICAL to flag — deployed-but-uncommitted is a real risk)
git status -s
# Branches & worktrees
git branch -a
git worktree list
# PRs (if gh available)
gh pr list --state all --limit 20 2>/dev/null
gh pr status 2>/dev/null
```

For **deployment state**, use read-only checks only (never deploy/seed from inside a handoff):
- `firebase hosting:channel:list 2>/dev/null`, `firebase functions:list 2>/dev/null` (or the project's equivalent)
- A `curl` against the live URL's health/data endpoint if one is known
- Otherwise, state what was deployed **this session** from the conversation, and clearly mark anything you could not independently verify.

> ⚠️ Pay special attention to **drift between what is DEPLOYED and what is COMMITTED/PUSHED/MERGED.** If prod is running code that lives only in the working tree, say so loudly — it is the highest-value fact in the handoff.

## Step 3 — Write the handoff document

Write to the project's canonical handoff file (default: the existing `*HANDOFF*.md`; if none, `HANDOFF.md` at repo root). Use this structure — include EVERY section, even if the answer is "n/a, because…":

1. **Header** — date, repo path, current branch, author note ("written by an agent at end of session X"), and a one-line "read these sections first."
2. **TL;DR / Mission** — what the project is and the single overriding goal + hard deadline.
3. **What happened since the last handoff** — narrative diff. What this session changed, decided, deployed, broke, fixed. Reference the prior handoff by name.
4. **Status by area** — a table or per-area breakdown covering at minimum: **Missions/Sprints**, **PRs**, **Merges**, **Deployments**, **Branches**, **Worktrees**, **Validations/Tests**. For each: state ✅ done / 🟡 in-progress / 🔴 blocked / ⬜ not-started, with the concrete evidence (commit SHA, URL, command output).
5. **VCS & deploy reality** — explicit answers to: Is it committed? Pushed to origin? Merged to main? Deployed? Call out any deployed-but-uncommitted drift.
6. **Architecture map** — enough for someone to navigate the code cold (key files, entrypoints, data model, prod wiring). Re-validate from the prior handoff.
7. **Gotchas / landmines** — the traps that waste hours. Carry forward still-true ones; add new ones from this session.
8. **How to run / validate locally** — exact commands, ports, env vars.
9. **The plan / next steps** — sequenced, with owners and exit criteria.
10. **Open questions for the user / next agent.**
11. **Reference docs & memory pointers.**

## Step 4 — Close out

- Do **NOT** commit or push the handoff unless the user explicitly asks.
- Tell the user the file path, a 3–5 bullet summary of the most load-bearing facts (especially any deploy/commit drift), and what the recommended next action is.
- If clarifying details would materially improve the handoff, ask the user before finalizing (not after).
