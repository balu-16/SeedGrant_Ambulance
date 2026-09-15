import type { MockSession } from "../types/models";
import { ApiError, apiLogin, apiMe, clearTokens, isApiEnabled } from "./api";

export interface AuthService {
  signIn(identifier: string, password: string): Promise<MockSession>;
}

export const authService: AuthService = {
  async signIn(identifier, password) {
    const id = identifier.trim();
    if (!id || !password) {
      throw new Error("Incorrect driver email or password. Please try again.");
    }
    if (!isApiEnabled()) {
      throw new Error(
        "App is not configured: missing backend URL (EXPO_PUBLIC_API_URL).",
      );
    }
    try {
      const login = await apiLogin(id, password);
      const role = (login.user?.role ?? "").trim().toLowerCase();
      if (role !== "driver") {
        await clearTokens();
        throw new Error(
          "This account is not a driver account. Please try again.",
        );
      }
      try {
        const me = await apiMe();
        const meRole = (me.role ?? "").trim().toLowerCase();
        if (meRole !== "driver") {
          await clearTokens();
          throw new Error(
            "This account is not a driver account. Please try again.",
          );
        }
        return { driverId: me.id, signedInAt: Date.now() };
      } catch (e) {
        // Login tokens are not trusted until the identity endpoint confirms
        // the same active driver account.  Do not enter the app on a partial
        // or unavailable /me response.
        await clearTokens();
        throw e;
      }
    } catch (e) {
      // Keep error handling stable in web bundles where duplicate module
      // instances can make `instanceof ApiError` unreliable.
      const apiError =
        e instanceof ApiError ||
        (typeof e === "object" &&
          e !== null &&
          "code" in e &&
          typeof (e as { code?: unknown }).code === "string");
      const errorCode = apiError ? (e as ApiError).code : "";
      const errorStatus = apiError ? (e as ApiError).status : 0;
      if (e instanceof Error && e.message.includes("not a driver account"))
        throw e;
      if (apiError && errorCode === "NETWORK_ERROR") {
        throw new Error("Backend unreachable. Check connection and retry.");
      }
      if (apiError && (errorCode === "UNAUTHORIZED" || errorStatus === 401)) {
        throw new Error(
          "Incorrect driver email or password. Please try again.",
        );
      }
      if (apiError && e instanceof Error && e.message) {
        throw new Error(
          `${e.message} (code ${errorStatus || errorCode}). Please try again.`,
        );
      }
      throw new Error("Login failed. Please try again.");
    }
  },
};
