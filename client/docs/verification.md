# Verification

Validated on 12 September 2026 with Node 24, Expo SDK 57, and Google Chrome on Linux.

## Automated checks

- TypeScript strict type checking: passed.
- ESLint: passed.
- Prettier format check: passed.
- 11 state/service tests: passed. Coverage includes launch routing, mock credentials, duplicate starts, priority sequencing, recovery without background replay, stop/release, logout, profile/settings updates, calendar filters, and persisted-data validation.
- 6 browser interaction tests: passed. Coverage includes all seven screens, onboarding controls, invalid login, password visibility, reload restoration, protected navigation, background/foreground simulation, History search/filters, Profile edits, confirmation settings, active logout cancellation, offline interactions, damaged-storage recovery, and short viewport use.
- Expo-compatible dependency check: passed.
- Expo Doctor: 21/21 checks passed.
- Android Hermes bundle export: passed. The generated bundle is under ignored `dist/`; this is not an APK or a native runtime test.
- Metro started successfully on port 8081; browser flows completed without observed JavaScript runtime errors.

## Visual review

All seven reference images were inspected before implementation and compared with the generated browser screenshots. The polish pass fixed image bounds, adjusted Login's scene scale, tightened Profile card spacing, aligned onboarding arrows to the trailing edge, and fitted priority-sign lettering. Artwork, captions, buttons, and forms are independently rendered so the UI can resize.

`docs/screenshots/` contains the seven screen captures plus active Home, a compact Profile, and scrolled Profile settings under larger text. Screenshots use 393×852 and 320×640 viewports. Login was also exercised at 360×420 to stress a reduced visible area. The larger-text check increases browser text metrics by 30%; native font scaling and the actual Android software keyboard still need device verification. The small lightning control visible in some captures belongs to Expo's browser development overlay, not the application UI.

## Native verification limit

No `adb`, Android emulator binary, or Android SDK was found in the environment. Consequently, Android device launch, physical swipe/Back gestures, native keyboard handling, system insets, TalkBack, and OS background/kill behavior were not verified on hardware. Their shared application logic is covered by tests, and the Android bundle compiles. A device or configured emulator is required for final native acceptance using `npm run android` or compatible Expo Go.

## Dependency audit

The installed stable Expo dependency tree reports 14 moderate npm audit findings, including transitive `uuid`/`xcode` and `decode-uri-component`/`query-string` chains. npm's proposed automatic fixes downgrade major Expo packages, so no forced downgrade was applied. These findings remain for upstream-compatible remediation; the audit is not represented as clean. No application backend, remote map tiles, location permission, or API credential is used.
