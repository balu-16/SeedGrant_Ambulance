import type { MockSession } from "../types/models";
import { ApiError, apiLogin, apiMe, clearTokens, isApiEnabled } from "./api";

export interface AuthService {
  signIn(identifier: string, password: string): Promise<MockSession>;
}

export const authService: AuthService = {
  async signIn(identifier, password) {
    const id = identifier.trim();
    if (!id || !password) {
      throw new Error(
        "Incorrect driver ID/email or password. Please try again.",
      );
    }
    if (!isApiEnabled()) {
      throw new Error(
        "App is not configured: missing backend URL (EXPO_PUBLIC_API_URL).",
      );
    }
    try {
      const login = await apiLogin(id, password);
      const role = (login.user?.role ?? "").trim().toLowerCase();
      if (role && role !== "driver") {
        await clearTokens();
        throw new Error("This account is not a driver account. Please try again.");
      }
      try {
        const me = await apiMe();
        const meRole = (me.role ?? "").trim().toLowerCase();
        if (meRole && meRole !== "driver") {
          await clearTokens();
          throw new Error("This account is not a driver account. Please try again.");
        }
        return { driverId: me.id, signedInAt: Date.now() };
      } catch (e) {
        if (e instanceof Error && e.message.includes("not a driver account")) throw e;
        return { driverId: id, signedInAt: Date.now() };
      }
    } catch (e) {
      if (e instanceof Error && e.message.includes("not a driver account")) throw e;
      if (e instanceof ApiError && e.code === "NETWORK_ERROR") {
        throw new Error("Backend unreachable. Check connection and retry.");
      }
      if (
        e instanceof ApiError &&
        (e.code === "UNAUTHORIZED" || e.status === 401)
      ) {
        throw new Error(
          "Incorrect driver ID/email or password. Please try again.",
        );
      }
      if (e instanceof ApiError && e.message) {
        throw new Error(`${e.message} (code ${e.status || e.code}). Please try again.`);
      }
      throw new Error("Login failed. Please try again.");
    }
  },
};
