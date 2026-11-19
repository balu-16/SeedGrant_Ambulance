# SeedGrant Ola Maps Implementation Plan

## 1. Scope and acceptance

Replace the embedded map basemaps in `admin/` and the basemap, hospital route, distance, and ETA in the Expo driver app in `client/`. Use the FastAPI service in `server/` for Ola Maps requests. The mobile map must work in Expo Go on SDK 57 and in the Expo browser preview.

- **Admin portal.** Render Ola behind live ambulance and junction markers on Admin Live Map, its session drawer, Hospital Live Tracking, and Police Junction Live. Use the role-filtered GPS, command, and junction feeds that already power those views.
- **Driver app.** Draw the route to the recorded destination hospital on the Home card and route sheet. Display driving distance and ETA from Ola. The external directions and SMS location actions use their existing OpenStreetMap links.
- **Emergency operations.** Use Ola outputs for display. Continue to drive emergency state and junction priority from the existing GPS and geofence pipeline. Exercise that pipeline with Ola down as part of acceptance.
- **Reference implementation.** Read `/home/balarakeshg16/Documents/Projects/delivery/server/src/adapters/maps/ola.ts`, its `config.ts`, and `scripts/maps-ola-smoke.ts`. Adapt the fixed provider origin, timeouts, response checks, request IDs, and secret handling to the Python service. Use SeedGrant's own Ola credentials.

## 2. Implementation order and agent ownership

1. Have the lead confirm the contracts in §4 and give all agents the same two fixtures. Use a successful directions response with a three-point polyline and a minimal MapLibre style with a relay-backed source. Use the public coordinates in §4 for fixtures and smokes.
2. Assign three parallel subagents separate working paths. The backend agent owns `server/` and the API and provider tests. The admin agent owns `admin/` and its browser tests. The Expo agent owns `client/` and its browser tests. The two frontend agents can start against contract fixtures while the backend agent builds the endpoints.
3. Have the lead handle any cross-project changes, review the combined diff, wire both frontends to the actual backend contract, run the integration checks, and collect the live smoke results. The lead coordinates changes to shared CI or deployment configuration when a concrete integration requirement calls for them.

## 3. Configuration and rollout switch

Use the ignored `server/.env` as the local source for Ola and Supabase credentials. Verify it is ignored with `git check-ignore server/.env` before writing it. Add these names to `server/.env.example` with blank credential placeholders.

| Setting | Value and use |
| --- | --- |
| `OLA_MAPS_PROJECT_ID` | Project ID from the supplied Ola credentials. |
| `OLA_MAPS_API_KEY` | Server key used for directions, style, and asset requests. |
| `OLA_MAPS_CLIENT_ID` | OAuth client ID from the supplied credentials. |
| `OLA_MAPS_CLIENT_SECRET` | OAuth client secret from the supplied credentials. |
| `OLA_MAPS_ENABLED` | Default `false`. Set `true` for an authorized integration environment with a working server key. |

- Use the screenshot from the implementation conversation or values already provisioned in `server/.env`. If neither is accessible, finish the code and tests with fixtures and report the live Ola smoke as pending credentials. The OAuth values are stored for the project. The API key is sufficient for the chosen integration. [Ola authentication docs](https://maps.olakrutrim.com/docs/auth)
- Model the API key and OAuth secret as `SecretStr` settings. Keep real values in the local ignored file and the backend's deployment secrets. The frontend configuration continues to point to SeedGrant through `VITE_API_URL` and `EXPO_PUBLIC_API_URL`.
- With maps disabled or a key missing, the map endpoints return `503 MAPS_UNAVAILABLE`. Allow FastAPI to start and serve its core endpoints. Use the existing isolated demo harness with test fixtures for map requests. The Supabase schema and Alembic revision already support the source data for these maps.

## 4. FastAPI contracts and Ola adapter

Register the map router under `/api/v1/maps` in `server/app/main.py`. Use the existing dependencies in `server/app/core/dependencies.py` for user and role checks and the existing success and error envelopes for JSON APIs. Keep provider request handling in one adapter using `httpx` and make its transport injectable for tests.

### Directions

`POST /api/v1/maps/directions` requires an authenticated `DRIVER` through the existing bearer token flow. The request contains these two WGS84 points.

```json
{
  "origin": { "latitude": 16.5058, "longitude": 80.6520 },
  "destination": { "latitude": 16.5193, "longitude": 80.6305 }
}
```

- Require finite numeric latitude and longitude in the legal ranges. Reject unset `(0, 0)` points. Use a validation response that gives a field and error type without echoing coordinate values. The current validation logger includes input values by default, so ensure the maps path omits them from logs.
- Send `POST https://api.olamaps.io/routing/v1/directions` with `origin` and `destination` formatted as `lat,lng`, `mode=driving`, `overview=full`, `steps=false`, and `alternatives=false`. Attach the configured `api_key` and a request ID server-side. Forward coordinates and routing options to Ola. [Ola API reference](https://maps.olakrutrim.com/apidocs)
- Normalize the primary route. Sum the legs' distance in meters and duration in seconds. Decode `overview_polyline` into ordered `{latitude, longitude}` points and validate the result. Check the precision, status values, and units against the Ola schema and smoke response. A documented no-route response has HTTP 200 with `{"success":true,"data":null}`.
- Use the existing `401`, `403`, and `422` outcomes for missing auth, a wrong role, and invalid input. Use `429 RATE_LIMITED` for a local limit and `503 MAPS_UNAVAILABLE` for disabled maps, an upstream quota response, timeout, rejection, or invalid provider response. Return a short error message suitable for the UI.

Example success fixture with synthetic distance and duration.

```json
{
  "success": true,
  "data": {
    "polyline": [
      { "latitude": 16.5058, "longitude": 80.6520 },
      { "latitude": 16.5140, "longitude": 80.6422 },
      { "latitude": 16.5193, "longitude": 80.6305 }
    ],
    "distance_m": 4500,
    "duration_s": 720
  }
}
```

### Style and assets

`GET /api/v1/maps/style` accepts signed-in `ADMIN`, `HOSPITAL`, `POLICE`, and `DRIVER` users. Return `data: { style, asset_token, expires_at }`, where `style` is a MapLibre style object and `expires_at` is an ISO 8601 UTC timestamp. Send `Cache-Control: no-store` on the grant response.

- Fetch the published `default-light-standard` Ola style through FastAPI. Verify the source, tile, font, and sprite resource paths against the live style when preparing fixtures. Rewrite their URL fields and any nested TileJSON tile templates to `/api/v1/maps/assets/...`. Preserve tile placeholders such as `{z}`, `{x}`, and `{y}`, sprite suffixes, and attribution. Resolve rewritten paths against the configured SeedGrant API base in each frontend. [Ola style setup](https://maps.olakrutrim.com/docs/sdks/web-sdk/latest/setup)
- Issue a five-minute signed bearer token with type `map-assets` and a user subject, using the existing JWT signing and verification code. Require this token type for `GET /api/v1/maps/assets/{resource_path:path}`. The session token grants access to the style endpoint and the scoped token grants access to map assets. Asset requests can verify the grant without a Supabase round trip for every tile.
- Build asset upstream requests from explicit, fixed Ola resource patterns. Validate each resource type and coordinate or filename parameter. Resolve to a verified Ola HTTPS host and vetted path. Reject arbitrary targets, unexpected path segments, and redirects. Apply the server key only to approved upstream requests. Stream or bound the response, preserve the correct media type, and keep the encoding header consistent with the returned bytes.
- In both renderers, attach the scoped bearer only to the configured SeedGrant asset path. Refresh the grant through the existing authenticated request client one minute before expiration while the map is mounted. Update the renderer's token without remounting or resetting its view. Clear map state on logout and show a recoverable message if a grant or style cannot load.

### Provider reliability and privacy

- Use a three-second total directions deadline and a five-second style and asset deadline, including any retry. Allow one retry inside that deadline for a transient transport failure or upstream `5xx`. On an upstream `429`, honor `Retry-After` when supplied and let the caller recover without an immediate repeat.
- Start with per-user limits of 6 directions and 12 style requests per minute. Allow normal tile bursts and cap in-flight upstream asset requests at 8 per process, with a separate budget from directions. Keep the limits in the maps layer and document them in the backend setup notes.
- Log operation, elapsed time, outcome, and request ID. Suppress HTTPX request URL logging for Ola calls because query strings contain the API key and precise coordinates. Keep provider response bodies, credentials, bearer tokens, and precise location data out of errors and diagnostics.

## 5. Admin web

1. Add `maplibre-gl` `5.24.1` and `@maplibre/maplibre-gl-leaflet` `0.1.4` to `admin/` and its lockfile. Lazy-load the base layer with the map views. Use one shared component to mount and dispose the MapLibre layer through Leaflet and show loading, error, and retry states. [MapLibre Leaflet adapter](https://github.com/maplibre/maplibre-gl-leaflet)
2. Replace the raster `TileLayerGuard` usages in the shared `MapView` and in both maps in `LiveMapPage`. Fetch the style through the portal's existing authenticated request service. Use React Query to share one in-memory style and grant renewal loop between the main map and drawer within the portal session.
3. Keep the Leaflet overlays and existing role queries as the source of the operational map. Verify marker colors and popups, marker-to-drawer selection, selected junction centering, GPS timestamps, stale-state indicators, and polling. On style, tile, or WebGL failure, show the reason in the map area while presenting the existing lists and any available Leaflet overlays. Expose a retry action and clear the message on recovery.
4. Use the configured API base for dev and Vercel. Verify same-origin API rewrites and cross-origin requests through the repository's existing origin allowlist when a separate API origin is configured. Remove the old OSM basemap URL helper and `VITE_TILES_URL` lookup after the four views use Ola.

## 6. Expo driver app

1. Read the exact SDK 57 docs required by `client/AGENTS.md`. Install `react-native-webview` using `npx expo install react-native-webview` and pin `maplibre-gl` to `5.24.1`. Expo Go on SDK 57 includes WebView 13.16.1. Use the SDK's WebView for Android and iOS and a platform-specific DOM implementation for the Expo web preview. [Expo SDK 57 WebView docs](https://docs.expo.dev/versions/v57.0.0/sdk/webview/)
2. Create a bundled local map document for native. Generate the document module from the installed MapLibre UMD JavaScript, stylesheet, and small renderer entry point with a deterministic Node script wired into package installation. Store generated output in an ignored path. Load static HTML with SeedGrant's configured API URL as the base and a policy that limits scripts, asset requests, and navigations to the bundled map and SeedGrant API. Use the compatible worker policy for the pinned MapLibre bundle. [WebView inline HTML reference](https://github.com/react-native-webview/react-native-webview/blob/master/docs/Reference.md#source)
3. Let the map document announce readiness. Pass validated JSON for the style, scoped token, marker coordinates, and route through the WebView bridge after it is ready. Keep the document stable across GPS and token updates. Route data and credentials belong in memory. Renderers should accept a common `LiveRouteMap` prop contract and use `[longitude, latitude]` for MapLibre geometry. Dispose the map and listeners when their view closes.
4. In `client/services/routing.ts`, replace direct OSRM fetching with the driver API request wrapper and map `distance_m` and `duration_s` to the existing display types. Add optional `AbortSignal` support through `requestCore` and its retry path, including listener cleanup. Exit promptly on cancellation before retry, refresh, or alert handling. Remove `EXPO_PUBLIC_OSRM_URL`, `EXPO_PUBLIC_TILES_URL`, and the `react-native-maps` dependency after replacing their last callers.
5. Compute the route once in Home and share it across the card and route sheet. Use a fresh, usable GPS fix and valid coordinates from the existing hospital catalog. Use the API's recorded hospital when restoring a linked active session. The picker sets the next trip's default hospital during an active session. A free-text or unlocated destination can keep its name while showing that a route is unavailable.
6. Request the first route when the active session, GPS fix, and destination are ready. Refresh at most once per 30 seconds within the same session and destination. Trigger a new request immediately when a new session or effective destination becomes ready. Cancel superseded requests and ignore late results. Clear the ETA and route when the session ends, the fix becomes stale, or the provider returns no usable route.
7. Draw the decoded route and real ambulance and hospital markers. Fit the camera on first successful route and on destination change. Update marker and route data as it arrives so routine GPS updates allow the driver to pan. If basemap rendering fails, show the route status and any available position information. If routing fails, show an unavailable ETA and keep GPS and emergency controls usable. Display traveled GPS distance separately from estimated route distance.

## 7. Verification

**Baseline verified on `638ab25`.** `DATABASE_URL` and `SYNC_DATABASE_URL` each returned `SELECT 1`. The anon and service-role keys each returned HTTP 200 from Supabase Auth settings. The live revision matched `0014_role_varchar_compat` and the relevant tables were present. The existing 164 backend, 32 admin, and 27 client tests passed, along with the client typecheck.

### Isolated automated checks

Set `OLA_MAPS_ENABLED=false` in the default backend test environment. Map tests enable the adapter with an injected mock transport and test-only key. Browser tests intercept map requests or use the local client mock backend.

| Area | Checks and acceptance |
| --- | --- |
| Backend provider | Use `httpx.MockTransport` fixtures for a multi-leg route, known decoded coordinates, no route, timeout, `429`, malformed responses, bad upstream authentication, and bounded retry. Assert request parameters and units. Verify that tests can run without provider credentials. |
| Backend API | Cover endpoint roles, invalid coordinates, grant expiration, wrong bearer scope, rejected asset paths, style and nested TileJSON rewriting, asset content types, disabled mode, and credential and coordinate redaction. Use the in-memory test DB and mocked MQTT. |
| Admin | Exercise all four views with intercepted style and asset fixtures. Check visible markers, popup/drawer interactions, role scoping, map error and recovery, stale GPS, and independently functioning live lists. |
| Expo | Cover GPS and destination readiness, response mapping, throttling, superseded responses, aborts, logout and stop cleanup, restored emergency destination, and unavailable ETA. Extend the existing Playwright mock backend with the maps contracts for a Home-card and route-sheet flow. |
| Emergency regression | Run the existing isolated simulator with map requests disabled or limited to failure fixtures. Verify start, GPS updates, signal-priority request and release, and stop through the same application entry points as normal use. |

Run the repo checks after the agents' changes are integrated.

| Project | Commands |
| --- | --- |
| `server/` | `uv sync --locked`, `uv run ruff check app tests`, `uv run mypy app`, `uv run pytest -q`. Run the isolated demo backend with `server/scripts/run_demo.sh` from the repo root for the simulator and portal browser journeys. |
| `admin/` | `npm ci`, `npm run lint`, `npm test`, `npm run build`, and `npm run test:e2e` with the seeded demo backend running. |
| `client/` | `npm ci`, `npm run lint`, `npm run typecheck`, `npm run format:check`, `npm test`, `SCREENSHOT_DIR=test-results/screenshots npm run test:e2e`, `npx expo install --check`, and `npm run export:android`. |

### Live, read-only checks

1. Load the existing `server/.env` through the backend settings. Recheck both Supabase database connections with `SELECT 1` and read the Alembic revision in a read-only transaction. Check the anon and service-role keys against the configured project's `GET /auth/v1/settings`. Record statuses and the revision only. Use the isolated demo database for migrations, seeding, and emergency journeys.
2. Use the Ola key from `server/.env` for a fixed public-coordinate smoke. Fetch the light style, request one vector tile referenced by it, and request a route between public points near Vijayawada such as the coordinates in §4. Confirm tile media type, a decodable polyline, and plausible distance and duration. Output outcomes and request IDs without credentials or full provider URLs.
3. Run the browser flows in Chromium and smoke the map on a device with the matching Expo Go SDK using `npx expo start --go`. Use a reachable development API and controlled GPS input. Check map labels and attribution, pins, route rendering, zoom and pan, ETA, and recovery after a map request fails. Record which Android and iOS devices were actually tested. An Android bundle export is a build check. Device rendering requires a device or emulator.

## 8. Release handoff

- Record tests that ran, their outcomes, and any live or device checks blocked by unavailable credentials or hardware. Verify the final diff and generated bundles for accidental credential exposure without printing secret values.
- Release the backward-compatible backend endpoints before frontend builds that depend on them. Use `OLA_MAPS_ENABLED` to stage the rollout and disable provider calls while investigating failures. Observe directions timeouts, rate limits, and style failures through the sanitized logs.
- Before enabling Ola for live ambulance operations, confirm that SeedGrant's Ola agreement covers advisory ambulance routing and authenticated tile delivery. Use public coordinates for provider smoke tests and isolated data for application journeys. Ola's published terms restrict safety-critical use. [Ola platform terms, section 6](https://maps.olakrutrim.com/legal/terms-and-conditions)

---

# SeedGrant Admin Portal: Detailed Implementation and Test Plan

## 1. Goal and agreed decisions

Build a reliable, polished **working prototype** for administrators, hospitals, and police officers. Reuse the existing React application in `admin/`; all web dashboard source, assets, and browser tests belong there. Make the backend and simulator changes needed for the dashboard to work end to end.

The portal must:

- Keep the current SeedGrant visual identity while making the experience smoother, more responsive, and easier to use.
- Use real backend data for normal operation and clearly identify simulated data.
- Work without physical hardware by using an explicitly enabled, isolated local simulator.
- Make every visible action functional or clearly unavailable, with accurate feedback about what happened.
- Protect hospital and junction boundaries on the server, not just in the interface.
- Preserve the existing uncommitted Raspberry Pi changes while adjusting any related command-contract code.

Physical cameras, physical traffic-light operation, real-world safety certification, production field deployment, and multi-junction green-corridor orchestration are future work. The prototype must not represent simulated state or an acknowledgement as proof that a physical signal changed.

## 2. Baseline and identified gaps

The repository already has three role-specific page sets, a FastAPI backend, a mobile driver application, and preliminary Pi code.

| Priority | Gap | Evidence and consequence |
| --- | --- | --- |
| Critical | Device command delivery and acknowledgement do not share a complete contract. | MQTT payloads omit the command ID used by the Pi acknowledgement request. Retries reuse a correlation ID that the Pi currently treats as already seen. |
| Critical | Manual override state is incomplete. | Holding a request updates the database without necessarily releasing a command that reached a device. A held request cannot currently be reissued through the existing action. |
| Critical | Hospital history follows the ambulance's current assignment. | Moving an ambulance can change which hospital can see its past emergencies. Existing records do not reliably identify their original owning hospital. |
| High | The live traffic pipeline is unfinished. | The Pi main loop sends heartbeats but does not run the camera worker or publish traffic telemetry. No physical hardware is available for this phase. |
| High | Authentication and session feedback need correction. | Session restoration can freeze in development mode; a failed refresh clears stored tokens without consistently clearing the signed-in UI. Portal tokens are stored in browser local storage. |
| High | Several screens promise more than their data provides. | The map does not fully use junction state; current command counts are derived from a historical analytics window; timelines, alerts, crossing metrics, filters, and exports are incomplete or misleading. |
| Medium | Existing account and registry workflows have gaps. | Existing users' hospital and junction assignments cannot be fully edited in the UI; users beyond the first 200 are not reachable from the current user table. |
| Medium | Usability and automated portal coverage are limited. | Responsive navigation, keyboard-accessible rows and dialogs, reduced-motion handling, clear stale-data feedback, and portal browser tests need work. |

Baseline verification from the review:

- `admin/: npm run build` and `npm run lint` passed. The build reported a large JavaScript chunk, and the icon font is approximately 4 MB.
- `server/: pytest` passed **117 tests**. The tests emitted warnings about the length of the test-only JWT key.
- The Pi cloud-link test file passed **9 tests**.
- These tests use mocks and isolated data; they do not establish that physical signal hardware works.

## 3. Target portal features

### 3.1 Administrator

- **Overview:** active emergency count, current pending command count, fleet size, online and offline devices, recent critical alerts, and links to the underlying records.
- **Live map:** active ambulance positions and junctions, with latest GPS time, device status, available telemetry, command state, and explicit stale or unavailable indicators. Select a marker or list item for detail.
- **Emergencies:** server-side search and filters, paginated history, complete available event timeline, and export of all filtered results.
- **Users:** create and edit users; change role, hospital, and police-junction assignments together; enable or disable accounts; reset passwords; search and paginate the complete directory.
- **Hospitals and fleet:** create and edit hospitals and ambulances, assign or unassign drivers and hospitals, update duty status, and explain conflicts without losing entered form data.
- **Junctions and devices:** register and edit junctions, inspect approaches, deactivate or delete only where permitted, register devices, inspect health and telemetry, and rotate device keys with a one-time reveal.
- **Commands and alerts:** inspect current and historical commands, delivery attempts, acknowledgements, timeouts, and applicable manual actions. Provide an in-portal alert feed with links to affected records.
- **Analytics, audit, and system:** show defined metrics and their time ranges, filter auditable actions, inspect broker and service health, and run an explicitly confirmed maintenance sweep.
- **Account:** provide an administrator password-change screen using the same self-service capability available to other portal roles.

### 3.2 Hospital

- Show only the hospital's owned active and historical emergencies, ambulances, and drivers.
- Provide live tracking, available command progress, emergency history and timeline, complete filtered CSV export, relevant in-portal alerts, fleet operations allowed by the backend, and password settings.
- Do not expose unrelated junction-device telemetry or another hospital's records. Explain when no hospital has been assigned.

### 3.3 Police

- Show only assigned junctions, their device health, available telemetry and detections, scoped command history, live emergency context, and analytics.
- Offer hold, reissue, and force-release controls only when the backend reports they are available. Require a reason and show the resulting delivery state.
- Provide account password settings and clear messaging when no junctions are assigned.

### 3.4 Shared experience

- Keep the existing navy/blue design, typography, and component language. Improve spacing, hierarchy, consistent buttons and forms, subtle transitions, and loading feedback.
- Support desktop, tablet, and narrow phone layouts. Provide a usable collapsible navigation, horizontally scrollable tables where needed, and appropriately sized dialogs.
- Make actionable rows keyboard-accessible; provide visible focus, dialog focus management and restoration, accessible labels, sufficient contrast, and reduced-motion support.
- Show the last successful refresh and data age. A failed request must never be displayed as a successful zero or empty state.
- Continue polling operational data every 10 seconds. Mark the portal connection stale after 30 seconds without a successful refresh; mark GPS stale after 30 seconds and use the backend's configured device-offline threshold for device state.
- Lazy-load maps and less frequently visited pages; reduce the icon-font payload to the icons actually used. Keep maps usable when external tile loading fails.

## 4. Implementation phases

### Phase 0: Establish a safe development baseline

1. Record the current working-tree changes and do not overwrite or reset them.
2. Run the existing portal build and lint, backend tests, and relevant Pi cloud tests before edits.
3. Add portal test tooling under `admin/`: unit/component tests and Playwright browser tests. Add corresponding package scripts and CI steps.
4. Keep the existing React, Vite, React Query, FastAPI, SQLAlchemy, PostgreSQL, and Alembic architecture unless a change below requires an addition.

**Acceptance:** existing checks still pass, and the new test commands run in CI without production credentials.

### Phase 1: Reliable and secure portal sessions

1. Correct the React authentication lifecycle so development-mode remounts, page reloads, expired sessions, logout, and failed refreshes always reach a usable state.
2. Add portal-specific login, refresh, and logout endpoints. Store an opaque, hashed refresh-session token server-side and use an HttpOnly, host-only cookie. Keep short-lived access tokens in memory.
3. Use `Secure` cookies in HTTPS deployments and allow the development-only HTTP exception on loopback. Apply `SameSite=Lax` and exact-origin checks. Set a separate readable, session-bound CSRF cookie at login; refresh and logout must send its value in an `X-CSRF-Token` header and validate it against the server-side session. Rate-limit the new login endpoints.
4. Associate portal access tokens with a revocable server-side portal session. Logout, password reset, account disablement, and password changes must invalidate the appropriate portal sessions. Preserve the driver's existing `/auth/*` token contract.
5. Use the Vite development proxy and a Vercel API rewrite before the SPA fallback so portal requests and cookies are same-origin. Coordinate refresh and logout across tabs; if coordination fails, require a clean sign-in rather than leaving a stale authenticated screen.
6. Remove the legacy `admin-portal:tokens:v1` local-storage entry on rollout and require those users to sign in again.

**Acceptance:** all three portal roles can sign in, reload, refresh, and sign out; driver accounts are rejected by the portal; expired or revoked sessions return to login; no refresh token is stored in local storage.

### Phase 2: Hospital ownership and account management

1. Add nullable `owner_hospital_id` to emergency sessions through a new Alembic migration. Capture the ambulance's hospital when a new session starts.
2. Do not automatically assign old records using the ambulance's current hospital. Old records with unknown ownership remain visible only to administrators.
3. Add an admin-only review action for an unassigned historical record. It must require a hospital and a reason, write an audit entry, and update only records whose ownership has not already been established.
4. Apply the ownership snapshot to hospital live views, history, alerts, analytics, timelines, and exports. Maintain existing driver ownership rules and police junction scoping.
5. Prevent transferring an ambulance to another hospital while its emergency is active. Lock the ambulance consistently during session creation and reassignment so concurrent requests cannot bypass the rule.
6. Complete the user editor: submit role and scope changes together, show server validation and conflicts, and provide server-side search, role/status filters, and pagination. Preserve last-admin and active-driver protections.

**Acceptance:** transferring a vehicle after an emergency does not transfer its old records; uncertain records are admin-only until reviewed; simultaneous emergency start and reassignment cannot create inconsistent ownership.

### Phase 3: Accurate data, timelines, alerts, and reports

1. Extend the live response with an uncapped total count, server observation time, and role-appropriate junction state. Preserve the current paged or bounded item list and make the cap visible.
2. Use latest GPS and telemetry timestamps to display freshness. Show a device's reported signal state only when telemetry actually provides it; otherwise show **Unknown**.
3. Extend emergency history filters to support status, date range, ambulance, junction, and, for admins, hospital. Apply authorization before filtering and pagination. Sort deterministically.
4. Make emergency timelines available to admins, the owning hospital, and the owning driver. Include only events supported by stored timestamps and audit records. Police command views remain limited to assigned junctions.
5. Add a server-side CSV endpoint using the same authorized filters and returning all matching rows in batches. Preserve CSV escaping and spreadsheet-formula protection, and audit the export without logging its contents.
6. Provide role-scoped in-portal alerts for emergency starts and endings, timed-out sessions, expired commands, and offline devices where the role is allowed to see them. Do not advertise email, SMS, or browser push delivery in this phase.
7. Show actual current pending commands (`PENDING` and `SENT` without acknowledgement) separately from historical analytics. Rename request-to-acknowledgement metrics accordingly; include sample counts and time-zone labels. Do not label them as physical crossing times.
8. Update documentation and UI text that currently claims cameras, signal state, full exports, or alerts are available when they are not.

**Acceptance:** counts, charts, timeline entries, filters, and exports match the underlying authorized records, including when there are more than 100 live sessions or more than one table page.

### Phase 4: Command lifecycle and isolated simulator

1. Define one additive command envelope for MQTT and HTTP polling: command ID, attempt number, junction ID, per-junction sequence, type, approach, correlation ID, issue time, and expiry time. Preserve the existing mobile API contract.
2. Persist the command and a retryable delivery record in the same database transaction before publishing. Retry unacknowledged, unexpired attempts; suppress superseded or expired attempts. Preserve ordering and make duplicate delivery and acknowledgement idempotent.
3. Fix the Pi command adapter and the simulator to deduplicate by command and attempt, reject older or expired attempts, and use the command ID for acknowledgement. Preserve the user's existing Pi MQTT-fallback changes.
4. Implement the following server-authorized actions:
   - **Hold:** prevent rearming the priority and queue a release if a prior request may have reached the device. Report release as pending until acknowledged.
   - **Reissue:** permit a held or expired request only for an active emergency and active junction, after any required release is acknowledged; issue a new attempt.
   - **Force release:** allow an open or held priority to be released, with retries and a visible pending or acknowledged result.
5. Require a reason, server-side role and junction checks, an audit entry, and clear conflict responses for each action. A command acknowledgement means receipt or handling by the device adapter; it does not prove that a physical light changed. Correct driver notification wording accordingly.
6. Build a local simulator that creates isolated demo users and records, sends a scripted ambulance GPS journey, registers a simulated device, publishes heartbeat/telemetry/detection data, polls commands, and acknowledges valid attempts.
7. Require an explicit demo flag, development environment, mock MQTT provider, and a dedicated local PostgreSQL demo database before the simulator can seed or send data. Validate these conditions in both the simulator and backend startup, and fail closed on a mismatch. The demo backend and simulator must not load the normal live `server/.env` or call live push services. Display **Simulation** throughout the portal.
8. Enforce manual-control availability on the backend: enable it for the isolated simulator after tests pass; keep it disabled for real devices until a later hardware-validation phase.

**Acceptance:** the simulated journey shows emergency creation, GPS updates, priority request, acknowledgement, hold, reissue, release, timeout, and recovery. Broker loss, duplicates, out-of-order messages, retries, and unavailable devices never produce a false success or a claimed physical green signal.

### Phase 5: Complete and polish the three portal roles

1. Implement the features in Section 3 using shared components and typed API clients inside `admin/`. Keep authorization checks on the backend.
2. Replace browser-native destructive confirmations with accessible confirmation dialogs showing the target and consequence. Display loading, success, conflict, permission, and retry states for every mutation.
3. Finish admin assignment editors, full pagination and search, one-time credential displays, the admin command log, and the account settings page.
4. Finish hospital and police views using only server-authorized records. Remove or correct controls and labels for features without a working delivery path.
5. Add responsive navigation, keyboard and screen-reader support, focus handling, reduced motion, and reliable map/list fallbacks.
6. Split heavy routes and map code, reduce the icon payload, and keep list rendering responsive with realistic prototype data volumes.

**Acceptance:** each role can complete its listed workflows, including error recovery, without a broken link, misleading placeholder, hidden unauthorized record, or nonfunctional action.

## 5. Public interfaces and data changes

JSON responses retain the existing `{ success, data, error }` envelope. The CSV export returns a streamed CSV file with the appropriate content type and download filename.

| Interface | Planned contract |
| --- | --- |
| `POST /api/v1/portal-auth/login` | Accept portal credentials, reject driver role, create a server-side portal session, set the protected cookie, and return a short-lived access token and user. |
| `POST /api/v1/portal-auth/refresh` | Validate origin, CSRF token, and refresh cookie; rotate the session secret and return a new access token. |
| `POST /api/v1/portal-auth/logout` | Revoke the portal session and clear its cookies. |
| `GET /api/v1/portal/status` | Return simulation/normal mode, server time, freshness settings, and whether the current role may use manual controls; never return secrets. |
| `GET /api/v1/admin/live` | Retain existing fields and add total count, observation time, and role-scoped device and telemetry state with timestamps. |
| `GET /api/v1/admin/emergencies` | Add validated server-side date, ambulance, junction, and hospital filters while retaining status, limit, offset, and total. |
| `GET /api/v1/admin/emergencies/export.csv` | Export all authorized records matching the same filters, with safe CSV escaping and no silent page-only truncation. |
| `PATCH /api/v1/admin/emergencies/{id}/hospital-ownership` | Admin-only assignment of a previously unknown owning hospital with a mandatory reason and audit entry. |
| `GET /api/v1/emergencies/{id}/timeline` | Retain driver access; add admin and verified owning-hospital access with complete available chronological events. |
| `POST /api/v1/junctions/{id}/override` | Retain action names and reason; return the requested action, command/attempt identity, and truthful pending or acknowledged delivery status. |
| MQTT and `GET /api/v1/commands/pending` | Return the same command ID, attempt, sequence, type, approach, correlation ID, and expiry fields. |
| `POST /api/v1/commands/{id}/ack` | Accept and validate the current attempt; retain a documented compatibility path for a legacy initial attempt while the Pi adapter is updated. |

Add Alembic migrations for hospital ownership, portal sessions, and durable command delivery state. Keep schema expansion separate from any data backfill. Do not rewrite existing migrations or infer historical ownership automatically. Document the migration order and a forward-fix strategy.

## 6. Test plan

### 6.1 Existing checks and migration tests

- Run the current portal build and lint, full backend suite, and relevant Pi cloud tests after each affected phase.
- Run new migrations on a fresh PostgreSQL database and a database upgraded from the current Alembic head. Verify that existing driver endpoints and records remain usable.
- Test the ownership migration with known, unknown, unassigned, active, and historical records. Verify that no automatic backfill assigns uncertain records to a hospital.

### 6.2 Backend and security tests

- Test every role against allowed and forbidden endpoints, including direct object IDs belonging to another hospital or junction.
- Test login, bad credentials, rate limiting, cookie attributes, CSRF and origin checks, refresh rotation, concurrent tabs, logout, revoked sessions, password changes, disabled users, and driver-client compatibility.
- Test ambulance reassignment before, during, and after an emergency, including concurrent start/reassignment requests.
- Test admin ownership review, required reason, audit history, and refusal to overwrite an established ownership snapshot.
- Test history filters, pagination, timelines, more than one export page, empty results, malicious CSV cells, and authorization on export.
- Test live counts above the item cap, missing and stale GPS, missing telemetry, offline devices, scoped alerts, and metric labels and calculations.

### 6.3 Command and simulator tests

- Verify the MQTT and HTTP envelopes carry the same command ID and attempt, and that publishing occurs only after the database transaction commits.
- Cover pending, sent, acknowledged, held, reissued, released, expired, and timed-out states; repeated actions; duplicate acknowledgements; and a release requested after hold.
- Simulate broker disconnect and reconnect, unavailable devices, process restart, delayed or out-of-order messages, expired attempts, and repeated delivery. Verify that obsolete commands are not applied.
- Verify that a release remains pending until acknowledged and that acknowledgement alone never produces a physical-signal confirmation.
- Confirm the simulator refuses production, nonlocal, or otherwise unapproved database and MQTT configurations, and cannot send real push notifications.
- Run the entire scripted demo journey against the real backend API and isolated demo database.

### 6.4 Portal unit, browser, and accessibility tests

- Add component tests for session boot and expiry, user scope editing, filters, pagination, export selection, data freshness, and mutation feedback.
- Add Playwright journeys for admin, hospital, and police, including unauthorized deep links and full simulated command actions.
- Test loading, empty, failed, stale, and recovered data; map-tile failure; slow requests; and network disconnect/reconnect.
- Test phone, tablet, and desktop layouts, keyboard-only navigation, dialog focus and restoration, visible focus indicators, and reduced-motion behavior.
- Confirm the production build uses route splitting and a smaller icon payload, and that the dashboard remains usable with realistic prototype-sized lists.

## 7. Rollout and definition of done

1. Deliver and verify schema expansion first, followed by a backward-compatible backend, then the same-origin portal proxy and updated UI. Existing portal users sign in again after the session-storage change.
2. Run the isolated simulator and all automated checks in CI and a local demo environment. Record how to start, reset, and stop the demo without touching a live database.
3. Update `admin/README.md` and `server/README.md` with setup, environment variables, role permissions, simulator use, migration notes, test commands, and known hardware limitations.
4. Treat the work as complete when the three role checklists work end to end, all new and existing checks pass, uncertain historical ownership is protected, demo data is unmistakable, and every displayed operational state is supported by its source.
5. Physical-device enablement requires a separate hardware integration and validation effort; no production deployment is part of this plan.
