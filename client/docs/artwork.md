# Local artwork

The built-in image generation tool created five separate assets from the supplied visual references. The original generated outputs remain under the Codex generated-images directory; copies are bundled in `assets/images/`. Runtime rendering never refers to that external directory.

| Asset                              | Reference              | Purpose                                                      |
| ---------------------------------- | ---------------------- | ------------------------------------------------------------ |
| `onboarding-01-emergency.png`      | `SplashScreen1.png`    | Front-facing ambulance, road, pale city, blank priority sign |
| `onboarding-02-location.png`       | `SplashScreen2.png`    | Rear ambulance, GPS route, hospital and location pin         |
| `onboarding-03-green-priority.png` | `SplashScreen3.png`    | Ambulance approaching connected green traffic signal         |
| `login-ambulance-city.png`         | `LoginPage.png`        | City street, ambulance and green signal behind login header  |
| `driver-avatar.png`                | New fictional portrait | Driver avatar used in headers and Profile                    |

React Native renders scene captions, sign lettering, status overlays, all screen copy, inputs, buttons, and navigation. Images contain no phone frames or app UI. Simple ambulance marks, heartbeats, icons, and the offline route map are rendered as vector UI. `assets/icons/app-icon.svg` is the editable code-native app icon; `node scripts/render-icon.cjs` renders its bundled PNG.

## Final generation prompts

### Onboarding 1

Create a local artwork asset for a React Native ambulance app, matching the illustration portion of the reference closely. Illustration-story, polished soft 3D painted medical city illustration, pale icy blue and white palette, navy details, red ambulance stripe. Portrait artwork 1024x1200 approximately. A large front three-quarter view white ambulance in the lower center driving toward viewer on a city road, blue windshield driver, red and blue emergency lights, soft blue high-rise city silhouettes, distant traffic. Upper left 40% must be very pale open sky reserved for live UI title overlay. Blue highway priority sign upper right should be blank, no lettering. Fade lower road smoothly to pure white at bottom edge. FILL the canvas with the scene. NO phone, device frame, borders, UI, buttons, labels, letters, words, watermarks. Match perspective and ambulance placement of the reference scene, not a screenshot. Save generated image.

### Onboarding 2

Generate only the illustration artwork from this app reference, no phone frame or UI. Soft polished 3D painted pale blue city medical illustration. Portrait 1024x1200 approximately. Rear three-quarter white ambulance with red stripe bottom left, a curving vivid blue GPS route on a pale isometric street map leads upward right to a white hospital building with red cross and a large red location pin. Subtle blue location pulse above ambulance. Upper left 40% pale sky empty space for separately rendered heading. Hospital at upper right, ambulance prominent lower left. Soft green parks, distant pale blue buildings. Fade bottom edge to pure white. No words, lettering, labels, badges, cards, ETA widgets, titles, buttons, screen borders, phone, watermarks. Keep very close to reference scene perspective and style.

### Onboarding 3

Create only scene artwork matching attached onboarding reference. Portrait about 1024x1200. Soft polished 3D painted city illustration, pale blue and white with medical red accents. Large rear three-quarter white ambulance lower left center moving away on urban road through junction. Tall traffic light at upper right glowing GREEN, connected device atop pole, small wireless arc symbol, blank blue road sign nearby. City skyline, trees, a few cars. Leave upper left 40% mostly pale open sky for React Native title overlay. Match reference subject placement, proportions and style. Fade bottom to white. NO typography, lettering, words, buttons, page dots, UI cards, phone frame, device, watermark. This is a full bleed illustration asset, not an app screenshot.

### Login

Generate a wide 1536x768 illustration artwork asset matching ONLY the city street illustration behind the login reference. No phone or UI. Soft painted 3D medical illustration in extremely pale icy blue, white, soft green trees. White ambulance with red stripe and red cross in lower center, front three-quarter side view driving right, wheels visible, small red blue lights. Tall traffic light on right edge lit GREEN. Distant low contrast blue city buildings and trees fill width, street lower quarter. Upper half fades toward almost white pale blue sky and has generous empty space. No text anywhere, no words, no signs with lettering, no logo badge, no labels, no form, no buttons, no device frame. Clean full bleed scene, same style and subject proportions as the reference artwork.

### Avatar

Create a square fictional Indian ambulance driver avatar for a medical app. Warm professional man around 32, short neat black hair, trimmed beard, friendly natural slight smile, navy ambulance uniform with narrow red shoulder piping. Head and shoulders centered, facing camera, light blue-gray seamless studio background. Polished realistic photographic portrait, soft even lighting. Entire head with generous safe margin for a circular crop. No text, no badges with lettering, no watermark. This person is fictional. 1024x1024.
