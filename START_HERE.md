# This is the ONE zip to use — ignore every earlier zip from this conversation

Every fix from this entire session, cross-checked against each other and
verified to compile cleanly, in one place. 18 files, same folder layout as
your project.

## Apply everything in one go (PowerShell)

```powershell
$project = "C:\Users\Prosperous Hotel\Downloads\My Projects\nova-platform\nova-platform"

Expand-Archive -Path "$HOME\Downloads\nova-master-fixes.zip" -DestinationPath "$HOME\Downloads\nova-master-fixes-extracted" -Force

Copy-Item "$HOME\Downloads\nova-master-fixes-extracted\*" -Destination $project -Recurse -Force
```

(fix both paths if your project folder or download location differ)

## Then, manual steps that can't be done by copying files in

`DELETE_THESE.md` — two things to delete by hand (a dead duplicate admin
route, and a real committed voice recording that shouldn't be in source
control).

## Then start everything

`HOW_TO_RUN_EVERYTHING.md` — backend first, confirm
`http://127.0.0.1:8000/health` actually loads before touching anything
else, then dashboard, then desktop agent, then (optionally) the browser
extension.

## Full list of what's fixed, by file

**Infrastructure (why nothing could connect at all):**
- `start-nova.ps1` — wrong DB password, wrong venv path
- `.gitignore` — was UTF-16-encoded, silently excluded nothing

**"Stops after a while" / can't hold a conversation:**
- `desktop-agent/core/conversation_state.py` — inactivity timer never
  re-armed after Nova finished speaking

**`QObject::startTimer`/`killTimer` "another thread" errors:**
- `desktop-agent/core/voice.py`, `desktop-agent/core/speech_manager.py` —
  the TTS worker thread was touching the conversation state machine
  directly instead of through signals

**Setup window opening behind everything else:**
- `desktop-agent/ui/onboarding.py`

**Alarms: Snooze/Dismiss did nothing; chat timing out on multi-step
requests:**
- `desktop-agent/core/api_client.py`

**"Can't do the things I told it to" (multi-step / hybrid requests):**
- `backend/app/services/orchestrator.py` — model never saw its own tool
  results, so "get the rate, then calculate with it" couldn't work; also
  added a system prompt (was completely missing) and current-time
  awareness (also completely missing)
- `backend/app/schemas/assistant.py`, `backend/app/api/v1/assistant.py` —
  the current-time field that makes reminders/alarms possible at all

**Prompt injection via scraped webpages:**
- `browser-extension/popup.js`, `browser-extension/api.js`

**"What app am I using?" / "review my code" — didn't exist as a
capability at all:**
- `desktop-agent/os_control/base.py`, `windows.py`, `macos.py`, `linux.py`
- `desktop-agent/core/ws_client.py`
- `backend/app/tools/os_file_tools.py`

## Audited and confirmed already solid (nothing to change)

Permissions system end-to-end, device pairing/revocation, the
confirm-pending-action endpoint, admin user/device/audit-log management,
the Next.js API proxy route, voice enrollment flow, browser extension
login, `macos.py`/`linux.py`'s OS controllers generally, mobile app auth,
and the download-center page (honestly says "no installers yet" instead
of faking one).

## Confirmed NOT built at all (not broken — just genuinely absent)

Knowledge base/RAG (spec §33), billing/subscriptions (§42), admin
CMS/branding config (§25–26). No fake UI for any of these — they simply
don't exist yet. Building these is real new feature work, not a bug fix;
say the word if you want to tackle one of them next.
