# Ambulance Driver (`client/` — Expo app in the SeedGrant monorepo)

An Android-first Expo SDK 57 frontend for the ambulance component of the Edge-AI Adaptive Traffic Management System. Seven screens reproduce the supplied `../reference/` designs. The app runs fully offline as a demo, and links to the FastAPI backend when `EXPO_PUBLIC_API_URL` is set (real login, GPS streaming, history, push notifications).

## Run

Requires Node.js 22.13+ (tested with Node 24) and npm.

```bash
cd client
npm ci
npm start
```

Scan the Metro QR code with a compatible Android Expo Go installation. With an Android SDK and an emulator or USB-connected device available, run `npm run android`. Use `npm run web` for a browser preview. Expo development loading needs access to Metro; after loading, application workflows work offline. An installed standalone Android build bundles the JavaScript and assets.

## Demo credentials

- Driver ID: `driver001`
- Email alternative: `driver001@example.com`
- Password: `123456`

These are public mock credentials used when the backend is unreachable or when signing in with the demo driver ID. Set `EXPO_PUBLIC_API_URL` in `.env` to link the app to the backend; with the API enabled, real accounts authenticate first and the demo credentials still work as a fallback. Profile edits do not change the login credentials.

## Project structure

```text
client/
├── app/                 # Expo Router entry, onboarding, login, and (tabs)
├── components/          # Shared controls, artwork primitives, timeline, navigation
├── features/
│   ├── onboarding/      # Three illustrated, swipeable pages
│   ├── auth/            # Validated mock login
│   ├── home/            # Emergency control and simulation status
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

START EMERGENCY begins a local simulation. Every three seconds in the foreground, it requests priority, grants green priority, releases priority, or crosses a junction. It then approaches the next mock junction. Simulation continues across tabs, pauses in the background, and resumes from the saved step after reopening without synthesizing background location events. Emergency duration uses elapsed wall-clock time. Stop releases outstanding priority and records one completed session in History. When the backend is linked, the same Start/Stop also opens and closes a server emergency session and streams GPS fixes to it; the location watch runs only while a session is active.

History filters use local calendar days, Monday-start weeks, and calendar months. The initial four fixtures use dates relative to first launch. Summary values derive from this month's actual saved sessions. Search matches hospital names; each card can expand to show every event.

Profile changes and settings persist locally. Password and support actions explain administrator-managed credentials. Logout ends any active backend emergency session, clears the local session and stored tokens, and preserves onboarding, completed history, settings, and profile edits. During an active emergency, logout requires confirmation and completes that emergency first.

Storage failures display a retry action. If a saved record is invalid or incompatible, the app offers an explicit reset of local demo data. Passwords are never saved or logged.

## Integration seams

- `services/api.ts`: real FastAPI client — JWT storage (SecureStore on native, AsyncStorage on web), single-flight refresh on 401, envelope unwrapping.
- `services/auth.ts`: backend login first, demo-credential fallback. `services/emergency.ts`: backend emergency session start/GPS/stop/history alongside the local simulator.
- `services/notifications.ts`: Expo push permission + token registration to `POST /push/register` (dev builds need `extra.eas.projectId` in `app.json`).
- The reducer owns emergency start/stop, event history, and profile edits; profile saves also PATCH `/auth/profile` when linked.
- `services/storage.ts`: versioned AsyncStorage state with ordered writes; `utils/persistence.ts` validates saved records before hydration.

Connection, ETA, hospital routes, driver identity, and signal states remain simulated. Location permission is requested only when an emergency session starts, and GPS is streamed to the backend only while a session is active. Patient records and external maps are absent.

## Packages and checks

Main packages: Expo 57, React Native 0.86, React 19, TypeScript 6, Expo Router, AsyncStorage, expo-location, expo-notifications, expo-secure-store, react-native-safe-area-context, react-native-svg, expo-linear-gradient, and Expo vector icons. ESLint, Prettier, tsx/Node tests, and Playwright support verification.

```bash
npm run typecheck
npm run lint
npm run format:check
npm test
npm run test:e2e       # Uses installed Google Chrome; starts/reuses Metro on 8081
npx expo install --check
npx expo-doctor
npm run export:android
```

Screenshots are saved by the browser tests to `docs/screenshots/`. These verify the web rendering of the shared native components; they are not Android emulator screenshots. See `docs/verification.md` for native verification limits.
