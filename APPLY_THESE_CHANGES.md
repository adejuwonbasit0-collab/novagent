# Batch 3 — reconciling this new zip with the two previous fix batches

This zip is a **different snapshot** of your project than the one I audited
before (it has real new work: server-side speaker profiles, the desktop
agent's speaker verification + conversation state machine, voice enrollment
UI, and its own independent `/admin` route separation). It was NOT built
starting from the batch-1/batch-2 fixes I sent you earlier, so those fixes
were missing here. This batch reapplies everything still relevant, against
this zip's actual current file contents, plus one new bug this zip
introduced.

## Files here (drop in at the same paths, overwriting in place)
- `.gitignore` — was still UTF-16-corrupted (silently matched nothing);
  replaced with UTF-8, plus a documented per-subproject `.venv/` convention
- `start-nova.ps1` — fixed **two** things: (1) still pointed at a root
  `venv/` instead of `backend/.venv`, (2) **new bug**: hardcoded Postgres
  credentials `postgres`/`postgres123` that don't match this zip's
  `docker-compose.yml`/`.env.example` (`nova`/`nova_password`) — this would
  have failed to connect on first run
- `backend/app/services/orchestrator.py` — still had no system prompt at
  all; added one that treats `<untrusted_external_content>` as data, never
  instructions (see batch 2's notes for the full reasoning)
- `browser-extension/popup.js` — updated "Summarize this page" to wrap
  scraped text in matching `<untrusted_external_content>` tags, with a
  guard against a page spoofing the closing tag
- `desktop-agent/os_control/windows.py` — `open_folder_in_application`'s
  VS Code fallback still used `shell=True` with a model-controlled path
  (Windows command injection); removed
- `desktop-agent/os_control/macos.py` — `send_notification`/`type_text`
  still interpolated raw strings into AppleScript source (injection) and
  `type_text` still used Python's `repr()` (not valid AppleScript escaping
  even before the security angle); both fixed with a real AppleScript
  string escaper
- `HOW_TO_RUN.md` — accurate step-by-step for this actual zip

## Manual deletions (already done in my working copy, do the same in yours)
1. **Delete `venv/` at the project root** if present — same 113MB
   accidentally-committed Windows venv as before, same corrupted-`.gitignore`
   root cause.
2. **Delete `dashboard/app/dashboard/admin/`** (3 files) — dead duplicate.
   This zip already has a real, separate `/admin` route
   (`app/admin/layout.tsx` + `dashboard/middleware.ts`, both well done, no
   changes needed there) but the old nested pages were never removed.
3. **Delete** any real committed audio under `backend/data/voice_samples/`
   except `.gitkeep`.
4. If using git: `git rm -r --cached venv dashboard/app/dashboard/admin
   backend/data/voice_samples` (except `.gitkeep`) once, then commit.

## What I did NOT touch in this pass
The new speaker-verification stack (`backend/app/models/speaker_profile.py`,
`api/v1/speaker.py`, `desktop-agent/core/speaker_embedding.py`,
`speaker_verification.py`, `conversation_state.py`, `ui/voice_enrollment.py`)
and the new `/admin` separation (`app/admin/layout.tsx`, `middleware.ts`)
were all already well-built on inspection — correct per-user scoping, no
trust of client-supplied IDs, real (if intentionally first-generation, and
honestly documented as such) speaker discrimination, a genuinely correct
state machine. No changes needed there.
