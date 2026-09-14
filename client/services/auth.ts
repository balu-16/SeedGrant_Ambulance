import type { MockSession } from "../types/models";
import { ApiError, apiLogin, apiMe, isApiEnabled } from "./api";

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
      await apiLogin(id, password);
      try {
        const me = await apiMe();
        return { driverId: me.id, signedInAt: Date.now() };
      } catch {
        return { driverId: id, signedInAt: Date.now() };
      }
    } catch (e) {
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
      throw new Error("Login failed. Please try again.");
    }
  },
};
