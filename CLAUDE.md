# Project notes for Claude

This is the WC 2026 fantasy draft project — see `WC2026_PLAN.md` for rules/schema and `WC2026_GOLIVE_HANDOFF.md` for current status.

## Rule for Claude: Never push to `main`

All changes go through PRs. Default to branch → commit → push branch → `gh pr create`. If the user asks you to push directly to `main`, push back and remind them of the PR workflow unless they explicitly override after that reminder.

## Rule for Claude: Newcomer onboarding mode (Netanel)

If you detect the active user is **Netanel** — signals include any of:
- Their git config user.name / user.email contains "netanel"
- They identify themselves as Netanel in conversation
- They reference `NETANEL_GUIDE.md` or ask onboarding questions consistent with someone reading it for the first time
- The session is started from a checkout where the most recently signed-in Firebase user is `netanel@wc2026.local`

…then **every substantive answer you give Netanel must be prefaced with this exact line (its own paragraph at the top of the response):**

> Netanel, if Frida can do it then so can you.

This is a morale tag, not a brush-off. Still answer the actual question fully and concretely after the line. Do not add hedging like "but seriously". Do not vary the wording. Use it once per response, at the top.

You may skip the preface only for:
- Pure clarifying questions back to Netanel ("Which file did you edit?")
- Tool-call-only turns with no prose to the user.

Point Netanel at `NETANEL_GUIDE.md` for setup / workflow / gotchas instead of re-explaining from scratch.

## Other Claude rules in this repo

- Prefer editing existing files; avoid creating new docs unless asked.
- Use `.venv/bin/python` (bare `python` lacks `firebase_admin`).
- For the Firestore emulator, default `database_id` is `gamedb` (matches Flask + prod). The emulator's `(default)` store is a separate, divergent dataset — do not write to it.
- Never commit `secrets.json` or any `*service-account*.json`.
