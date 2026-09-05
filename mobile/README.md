# Nova Mobile

Expo (React Native) app — the same account, backend, and assistant as the
web dashboard, browser extension, and desktop agent. Login, an assistant
chat screen (with the same confirmation-modal flow as every other client),
and a reminders screen.

## Layout

```
App.tsx              root — auth gate + lightweight tab switcher (no
                       react-navigation dependency, kept minimal on purpose)
lib/
  api.ts               request/token/refresh logic — same shape as the
                       dashboard's and extension's clients, backed by
                       expo-secure-store (iOS Keychain / Android Keystore)
                       instead of localStorage or chrome.storage
  theme.ts              shared color tokens, matching every other client
screens/
  LoginScreen.tsx
  RemindersScreen.tsx   pull-to-refresh list, inline add
  AssistantScreen.tsx    chat + confirmation modal
```

## Setup

```bash
npm install
npx expo start
```

Scan the QR code with Expo Go, or run `npx expo start --android` /
`--ios` with a configured emulator. Point it at a non-default backend by
calling `setBackendUrl()` from `lib/api.ts` (a real settings screen for
this is a reasonable next addition — not built yet).

## Verified

This sandbox has no iOS/Android emulator and no network access to Expo's
own versioning API (`api.expo.dev`), so testing here worked in layers,
each one real rather than assumed:

1. **`npx tsc --noEmit`** — zero type errors across the whole app.
2. **`npx expo export --platform web`** — the actual Metro bundler
   compiled all 170 modules (`App.tsx`, all three screens, `lib/api.ts`,
   `lib/theme.ts`) into a working production bundle with zero errors. This
   exercises real import resolution and real JSX/TS compilation, not just
   a syntax check.
3. **Loaded the real exported bundle into a DOM environment (jsdom)** and
   confirmed it executes without a top-level crash, and that React
   actually mounts and reaches real application logic (`App`'s
   `checkAuth()` calling into `lib/api.ts`'s `isLoggedIn()`). It then hit
   a genuine platform limitation: `expo-secure-store`'s **web-platform**
   shim isn't fully functional outside a real browser. This is a real
   finding, not swept under the rug — but it's specific to the web
   export, which was only ever a bundler-testing convenience here, not an
   intended distribution target (this app isn't listed as a web app
   anywhere; only iOS/Android). Real iOS/Android builds use
   `expo-secure-store`'s native implementation (actual Keychain/Keystore),
   a completely different, well-established code path unaffected by this.
4. **The part that actually matters — `lib/api.ts`'s own logic — was
   tested directly against a live backend**, independent of the
   web-platform SecureStore gap: compiled `api.ts` standalone, swapped in
   an in-memory mock for `expo-secure-store` (standing in for what the
   real native Keychain/Keystore module does), and ran it against a real
   running backend instance. Register, login, `/me`, create reminder,
   list reminders all succeeded. Then — the harder case — forged a
   genuinely expired access token, kept the real refresh token, called
   `listReminders()` again, and confirmed it silently refreshed and
   returned real data, with a verified-different access token written
   back afterward. Then logout, confirmed `isLoggedIn()` correctly
   returned false.

What wasn't (and couldn't be, in this environment) verified: actual
on-device rendering, touch interaction, or the real native
Keychain/Keystore SecureStore implementation itself — that one is Expo's
own well-established module, not custom code written here.

## Not built yet

- Push notifications for reminders
- A real settings screen for backend URL configuration (currently
  code-only via `setBackendUrl()`)
- Biometric unlock for the app itself (separate from the backend's own
  voice-authentication spec section, which isn't built anywhere yet)
- EAS build configuration for actual app store distribution
