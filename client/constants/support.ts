// Support contacts — override via EXPO_PUBLIC_SUPPORT_* in EAS builds.
// Empty by default so placeholder phone/email never ships to prod; UI hides
// Call/Email buttons when unset (see ProfileScreen).
const _extra = (process as any)?.env ?? {};
export const SUPPORT_PHONE: string = _extra.EXPO_PUBLIC_SUPPORT_PHONE ?? "";
export const SUPPORT_EMAIL: string = _extra.EXPO_PUBLIC_SUPPORT_EMAIL ?? "";
