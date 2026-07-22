---
name: pickup-handoff
description: Pick up an existing handoff to resume a project cold. Reads the latest handoff, VALIDATES every claim against live repo/deploy reality (branches, worktrees, commits, merges, deployments, file/line refs), produces a confirmed/mismatch/unverified report, then asks the previous agent (via the user) a short list of clarifying questions so you start 100% aligned. Use when the user says "pick up the handoff", "onboard from the handoff", or "validate the handoff before we continue".
---

# Pick up handoff — validate, reconcile, align

Your job: become the new owner of this project with **zero blind trust**. A handoff is a claim about a past moment; code, branches, and deployments may have drifted since. Verify before you build on it. This skill is **read-only** — do not change code, deploy, or commit while picking up.

## Step 1 — Find and read the handoff

```bash
ls -t *HANDOFF*.md **/*HANDOFF*.md 2>/dev/null
```
Read the most recent one in full. Also read the project auto-memory (`~/.claude/projects/<slug>/memory/MEMORY.md` + `project_*.md`) and skim referenced docs (PLAN, SPRINTS, PRODUCT_SPEC) it points to.

## Step 2 — Validate EVERY checkable claim against live reality

Go claim-by-claim. For each, run the actual check and record the verdict: **✅ CONFIRMED**, **❌ MISMATCH** (state expected vs actual), or **⚠️ UNVERIFIABLE** (and why).

- **Branches** the handoff names exist and point where it says:
  ```bash
  git branch -a
  git log --oneline -5 <branch>
  git rev-list --left-right --count origin/<branch>...<branch>
  ```
- **Worktrees** match what's described (paths, HEADs, stale ones):
  ```bash
  git worktree list
  ```
- **Commits / merges**: the SHAs it cites exist; "merged to main" / "pushed" claims are true:
  ```bash
  git log --oneline main..HEAD | head -40   # unmerged commits
  git show -s <sha>                          # cited commits exist
  git status -s                              # uncommitted drift vs what handoff implied
  ```
- **Deployments**: hit the live URL / list functions (read-only). Confirm the deployed thing actually responds as the handoff claims. Flag deployed-but-uncommitted drift loudly.
- **File / line references**: spot-check the important ones with `grep`/Read — line numbers drift, names get renamed. A handoff that says "the gate is at api_wc.py:1046" is a claim to verify, not a fact.
- **Data/state claims** (counts, seeded leagues, accounts): verify against the live system if creds/tools allow; otherwise mark ⚠️.

## Step 3 — Produce the validation report

Output a concise report grouped by area (Branches, Worktrees, Commits/Merges, Deployments, Code refs, Data/state). For each claim: the verdict + evidence. Put **❌ mismatches and ⚠️ unverifiables at the top** — those are what threaten alignment.

## Step 4 — Ask the previous agent (via the user) what you can't resolve

Build a SHORT list of high-leverage questions — only things you genuinely cannot determine from the repo and that would change how you proceed. Good categories:
- Ambiguities the handoff left open or that contradict live state (the mismatches from Step 2).
- Intent/rationale you can't infer ("why was X done this way", "is the deployed-but-uncommitted code intentional or should I commit it").
- Decisions pending with the user (dates, scope, onboarding model).
- Anything the handoff explicitly punted to "confirm with the user."

Use the `AskUserQuestion` tool for the top questions (give recommended options where you can), and list any remaining ones as plain text. Do **not** ask things you can answer yourself by reading the repo — answer those silently and only report the result.

## Step 5 — State your readiness

Close with: "I'm aligned on X, Y, Z (confirmed); blocked/uncertain on A, B (pending your answers)." Then stop and wait — do not start implementation until the user resolves the open questions.
