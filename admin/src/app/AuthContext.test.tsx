/**
 * Unit tests — AuthContext: driver-role rejection on login (client guard over
 * the server's 403) and the session-event handler clearing the user + cache
 * (fixes the stale authenticated screen on mid-session 401 / other-tab
 * logout).
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "@/app/AuthContext";
import { useAuth } from "@/app/auth-context";
import { ApiError } from "@/services/ApiError";
import type { AuthUser } from "@/types/api";

vi.mock("@/services/portalAuth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/services/portalAuth")>();
  return {
    ...actual,
    portalLogin: vi.fn(),
    portalLogout: vi.fn(async () => undefined),
    portalRefresh: vi.fn(async () => {
      throw new ApiError(
        "Session expired — please log in again",
        401,
        "UNAUTHORIZED",
      );
    }),
    onSessionEvent: vi.fn(() => () => undefined),
  };
});

const { onSessionEvent, portalLogin, portalLogout } = await import(
  "@/services/portalAuth"
);

function Harness({ email }: { email: string }) {
  const { user, booting, login } = useAuth();
  if (booting) return <div>booting</div>;
  return (
    <div>
      <div data-testid="user">{user?.email ?? "signed-out"}</div>
      <button
        type="button"
        onClick={() =>
          void login(email, "password-goes-here").catch(() => undefined)
        }
      >
        login
      </button>
    </div>
  );
}

function mount(email: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <Harness email={email} />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("AuthContext", () => {
  beforeEach(() => {
    vi.mocked(onSessionEvent).mockImplementation(() => () => undefined);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("rejects driver accounts on login (client guard) and signs the tab out", async () => {
    vi.mocked(portalLogin).mockResolvedValue({
      id: "d1",
      email: "driver@demo.io",
      role: "driver",
    });
    mount("driver@demo.io");
    await userEvent.click(await screen.findByRole("button", { name: "login" }));
    await waitFor(() => expect(portalLogout).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.getByTestId("user").textContent).toBe("signed-out"),
    );
  });

  it("clears the signed-in user when a session event (expired/logout) fires", async () => {
    // Capture the listener AuthProvider registered.
    const listeners: ((e: { type: "logout" | "expired" }) => void)[] = [];
    vi.mocked(onSessionEvent).mockImplementation((listener) => {
      listeners.push(listener);
      return () => undefined;
    });
    vi.mocked(portalLogin).mockResolvedValue({
      id: "a1",
      email: "admin@demo.io",
      role: "admin",
    } satisfies AuthUser);

    mount("admin@demo.io");
    await userEvent.click(await screen.findByRole("button", { name: "login" }));
    await waitFor(() =>
      expect(screen.getByTestId("user").textContent).toBe("admin@demo.io"),
    );

    // Another tab logs out / session revoked → broadcast → clear user+cache.
    for (const listener of listeners) listener({ type: "expired" });
    await waitFor(() =>
      expect(screen.getByTestId("user").textContent).toBe("signed-out"),
    );
  });
});
