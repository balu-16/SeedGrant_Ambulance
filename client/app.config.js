// Dynamic Expo config — lets EAS Build inject google-services.json via a
// file-type EAS variable while local runs fall back to the gitignored file.
// See https://docs.expo.dev/eas/environment-variables/usage/
//
// EAS file vars are exposed as a path (e.g. GOOGLE_SERVICES_JSON=/tmp/...json).
// Visibility must be plaintext/sensitive (NOT secret) so it is available
// during config resolution.
const appJson = require("./app.json");

module.exports = function () {
  const expo = appJson.expo;
  return {
    ...expo,
    android: {
      ...expo.android,
      googleServicesFile:
        process.env.GOOGLE_SERVICES_JSON || "./google-services.json",
    },
  };
};
