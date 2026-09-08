# READ THIS FIRST

I checked the zip you just uploaded against the very first one you sent.
Every file is byte-for-byte identical except `api_client.py` — none of the
fixes from this whole conversation have actually made it into your project
yet. That's the entire reason "stopping after a while" and "can't do the
things I told it to" are still happening: the code with those fixes has
only existed in the zips I sent you, not in the project you're running.

This zip has ALL of them combined in one place, 14 files, laid out in the
exact same folder structure as your project. Nothing to merge or figure
out — each file here replaces the one at the same path in your project,
completely.

## Apply everything in one go (PowerShell)

Replace the path on the first line with your actual project folder if
it's different:

```powershell
$project = "C:\Users\Prosperous Hotel\Downloads\My Projects\nova-platform\nova-platform"

Expand-Archive -Path "$HOME\Downloads\nova-all-fixes.zip" -DestinationPath "$HOME\Downloads\nova-all-fixes-extracted" -Force

Copy-Item "$HOME\Downloads\nova-all-fixes-extracted\*" -Destination $project -Recurse -Force
```

(Adjust the zip filename/path to wherever your browser actually saved it.)

That's it — every file in this zip lands exactly where it needs to be,
overwriting the broken version already there.

## Then do the two manual deletions (can't be done by copying files in)

See `DELETE_THESE.md` in this zip.

## Then restart everything, in order

See `HOW_TO_RUN_EVERYTHING.md` in this zip — backend first, confirm
`http://127.0.0.1:8000/health` loads, then dashboard, then desktop agent.

## What's actually in here

- `.gitignore`, `start-nova.ps1` — the Postgres credential/venv-path bug
  that was causing the WebSocket spam in the first place
- `desktop-agent/core/conversation_state.py` — the "stops after a while"
  fix (timer wasn't re-arming after Nova finished speaking)
- `desktop-agent/core/voice.py`, `speech_manager.py` — the
  `QObject::startTimer`/`killTimer` cross-thread errors
- `desktop-agent/ui/onboarding.py` — sign-in window opening behind other
  windows
- `desktop-agent/core/api_client.py` — chat timeout, plus Snooze/Dismiss
  on alarms (were calling methods that didn't exist)
- `backend/app/services/orchestrator.py`, `backend/app/schemas/assistant.py`,
  `backend/app/api/v1/assistant.py` — the "can't do the things I told it
  to" fix: multi-step requests ("get the rate, then calculate with it")
  couldn't work because the model never saw its own tool results; also
  added a system prompt (was completely missing) and current-time
  awareness (also completely missing, so it couldn't handle "remind me
  at 6" at all)
- `browser-extension/popup.js`, `api.js` — matching time-awareness fix,
  plus a prompt-injection guard on page content
