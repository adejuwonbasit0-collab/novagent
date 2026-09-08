# Manual deletions for this batch

A zip of fixes can only add/overwrite files, not remove them — do these two
by hand (or `git rm`) after dropping in the files above.

1. **`dashboard/app/dashboard/admin/`** (3 files: `page.tsx`,
   `ai-provider/page.tsx`, `settings/page.tsx`) — dead duplicate. The real,
   separated admin section is `dashboard/app/admin/` (with its own layout,
   middleware, and distinct dark-red shell) — that one's correctly built
   and needs no changes. This nested copy under `/dashboard/admin` is the
   exact anti-pattern spec section 23 says not to do (admin hidden inside
   the normal user dashboard shell instead of a genuinely separate route).
   Nothing in the app links to it. It's not a live security hole — the
   backend's `get_current_admin` dependency still rejects non-admin API
   calls from it either way — but it's confusing dead code sitting exactly
   where the spec says admin must NOT be, so it should go.

2. **Real committed voice sample audio**: there's an actual `.webm`
   recording committed at
   `backend/data/voice_samples/6b83b373-a327-4419-a664-c164c678c55b/`.
   That's a real user's biometric voice data sitting in source control.
   Delete it (keep `.gitkeep`). If this repo has git history, the file
   needs to be purged from history too (`git filter-repo` or equivalent),
   not just deleted in a new commit — otherwise it's still recoverable
   from any earlier commit/clone.
   `VOICE_STORAGE_DIR` should never point inside the repo tree in the
   first place; double-check `backend/.env`'s value isn't accidentally
   `./data/voice_samples` relative to a path git tracks in production.

If using git for both: `git rm -r --cached dashboard/app/dashboard/admin` and
`git rm --cached backend/data/voice_samples/<uuid>/*.webm`, then commit.
