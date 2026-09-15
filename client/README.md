# Ambulance Driver (`client/` — Expo app in the SeedGrant monorepo)

An Android-first Expo SDK 57 frontend for the ambulance component of the Edge-AI Adaptive Traffic Management System. Seven screens reproduce the supplied `../reference/` designs. The app requires a backend link for real login — set `EXPO_PUBLIC_API_URL` to the bare backend origin (e.g. `https://seedgrant-backend.onrender.com`, **no** `/api/v1` suffix; the client appends it). Without it the app shows an "App not configured" screen and login refuses.

## Run

Requires Node.js 22.13+ (tested with Node 24) and npm.

```bash
cd client
npm ci
npm start
```

Scan the Metro QR code with a compatible Android Expo Go installation. With an Android SDK and an emulator or USB-connected device available, run `npm run android`. Use `npm run web` for a browser preview. Expo development loading needs access to Metro; after loading, application workflows work offline. An installed standalone Android build bundles the JavaScript and assets.

## Local mock credentials

- Email: `driver001@example.com`
- Password: `123456`

These credentials are used by the local Playwright mock only. Set `EXPO_PUBLIC_API_URL` in `.env` (bare origin, no `/api/v1` suffix) or via the EAS dashboard (preview/production) to link the app to the backend; real driver accounts authenticate by email and non-driver roles are rejected. EAS `env` in `eas.json` overrides `.env` at build time — rebuild or EAS Update after changing dashboard vars. Profile edits do not change the login credentials.

## Project structure

```text
client/
├── app/                 # Expo Router entry, onboarding, login, and (tabs)
├── components/          # Shared controls, artwork primitives, timeline, navigation
├── features/
│   ├── onboarding/      # Three illustrated, swipeable pages
│   ├── auth/            # Validated backend login
│   ├── home/            # Emergency control and live status
│   ├── history/         # Sessions, filters, search, event details
│   └── profile/         # Driver/ambulance editors and settings
├── assets/
│   ├── images/          # Five generated images and raster app icon
│   └── icons/           # Editable SVG app icon
├── constants/           # Colors, shadows, local asset mapping
├── hooks/               # Typed state access
├── services/            # API client (refresh/401 handling), auth, tracking, fixtures, storage
├── store/               # Reducer, persistence hydration, foreground lifecycle
├── types/               # Domain models
├── utils/               # Dates, history filtering, saved-data validation
├── tests/               # State tests and browser interaction tests
├── scripts/             # Rebuild app icon from its vector source
└── docs/                # Artwork provenance, verification, screenshots
```

## Behavior

First launch shows onboarding. Next, page dots, swiping, Skip, and Get Started work. Completing or skipping onboarding persists that choice. Returning signed-out users see Login, and returning signed-in users see Home.

START EMERGENCY opens a backend emergency session and streams real GPS fixes while the session is active. The backend decides when to request and release junction priority. The session id and active state survive app reloads, and Stop waits for the backend to confirm the session and priority release before saving it to History. The local mock backend used by browser tests implements the same contract.

History filters use local calendar days, Monday-start weeks, and calendar months. The initial four fixtures use dates relative to first launch. Summary values derive from this month's actual saved sessions. Search matches hospital names; each card can expand to show every event.

Profile changes and settings persist locally. Password and support actions explain administrator-managed credentials. Logout ends any active backend emergency session before clearing the local session and stored tokens. If the backend cannot confirm priority release, logout remains pending so the app does not claim the emergency ended.

Storage failures display a retry action. If a saved record is invalid or incompatible, the app offers an explicit reset of local state. Passwords are never saved or logged.

## Integration seams

- `services/api.ts`: real FastAPI client — JWT storage (SecureStore on native, AsyncStorage on web), single-flight refresh on 401, envelope unwrapping.
- `services/auth.ts`: email-only backend login with fail-closed identity verification. `services/emergency.ts`: backend emergency session start/GPS/stop/history.
- `services/notifications.ts`: Expo push permission + token registration to `POST /push/register` (dev builds need `extra.eas.projectId` in `app.json`).
- The reducer owns emergency start/stop, event history, and profile edits; profile saves also PATCH `/auth/profile` when linked.
- `services/storage.ts`: versioned AsyncStorage state with ordered writes; `utils/persistence.ts` validates saved records before hydration.

Connection, ETA, hospital routes, and signal states are prototype-level integrations. Location permission is requested only when an emergency session starts, and GPS is streamed to the backend only while a session is active. Patient handoff and external maps are optional demo helpers.

## Packages and checks

Main packages: Expo 57, React Native 0.86, React 19, TypeScript 6, Expo Router, AsyncStorage, expo-location, expo-notifications, expo-secure-store, react-native-safe-area-context, react-native-svg, expo-linear-gradient, and Expo vector icons. ESLint, Prettier, tsx/Node tests, and Playwright support verification.

```bash
npm run typecheck
npm run lint
npm run format:check
npm test
npm run test:e2e       # Uses Playwright Chromium; starts/reuses Metro on 8081
npx expo install --check
npx expo-doctor
npm run export:android
```

Screenshots are saved by the browser tests to `docs/screenshots/`. These verify the web rendering of the shared native components; they are not Android emulator screenshots. See `docs/verification.md` for native verification limits.
