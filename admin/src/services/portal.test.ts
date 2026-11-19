/**
 * Unit tests — services/portal.ts: the emergency filter param builder
 * (contract §3) and the server CSV export (fetch with Authorization → blob →
 * download, server Content-Disposition filename).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  emergencyFilterParams,
  exportEmergenciesCsv,
} from "@/services/portal";
import { clearSession, setSession } from "@/services/portalAuth";
import type { AuthUser } from "@/types/api";
import type { EmergencyFilters } from "@/services/portal";

const USER: AuthUser = { id: "u1", email: "admin@demo.io", role: "admin" };

describe("emergencyFilterParams", () => {
  it("encodes every contract §3 filter and skips empties", () => {
    const filters: EmergencyFilters = {
      status: "COMPLETED",
      from: "2026-01-01",
      to: "2026-01-31",
      ambulance_id: "amb-1",
      junction_id: "j-9",
      hospital_id: "h-2",
    };
    const q = emergencyFilterParams(filters);
    expect(q.get("status")).toBe("COMPLETED");
    expect(q.get("from")).toBe("2026-01-01");
    expect(q.get("to")).toBe("2026-01-31");
    expect(q.get("ambulance_id")).toBe("amb-1");
    expect(q.get("junction_id")).toBe("j-9");
    expect(q.get("hospital_id")).toBe("h-2");
    expect([...q.keys()].sort()).toEqual([
      "ambulance_id",
      "from",
      "hospital_id",
      "junction_id",
      "status",
      "to",
    ]);
  });

  it("drops empty strings and undefined values (no spurious params)", () => {
    const q = emergencyFilterParams({
      status: "",
      from: undefined,
      junction_id: "j-1",
    });
    expect([...q.keys()]).toEqual(["junction_id"]);
    expect(q.toString()).toBe("junction_id=j-1");
  });

  it("returns an empty query for no filters", () => {
    expect(emergencyFilterParams({}).toString()).toBe("");
  });
});

describe("exportEmergenciesCsv", () => {
  beforeEach(() => {
    setSession("tok-1", USER);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    clearSession();
  });

  function mockExport(status = 200, filename = "emergencies-20260101-000000UTC.csv") {
    const blob = new Blob(["emergency_id,status\r\nabc,COMPLETED\r\n"], {
      type: "text/csv;charset=utf-8",
    });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      headers: { get: (k: string) => (k === "Content-Disposition" ? `attachment; filename="${filename}"` : null) },
      blob: async () => blob,
      json: async () => ({ success: false, error: { code: "X", message: "denied" } }),
    } as unknown as Response);
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("fetches the export endpoint with the Bearer token and filter params, then downloads the blob", async () => {
    const fetchMock = mockExport();

    const created: string[] = [];
    const objectUrl = "blob:mock-url";
    const createObjectURL = vi.fn(() => {
      created.push("url");
      return objectUrl;
    });
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      value: createObjectURL,
      configurable: true,
      writable: true,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      value: revokeObjectURL,
      configurable: true,
      writable: true,
    });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    await exportEmergenciesCsv({ status: "COMPLETED", junction_id: "j-9" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/admin/emergencies/export.csv");
    expect(url).toContain("status=COMPLETED");
    expect(url).toContain("junction_id=j-9");
    expect(url).not.toContain("limit=");
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer tok-1",
    );
    // Download goes through the blob (never a bare <a href> to the API).
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(click.mock.instances[0]).toBeInstanceOf(HTMLAnchorElement);
    expect(revokeObjectURL).toHaveBeenCalledWith(objectUrl);
  });

  it("uses the server's Content-Disposition filename", async () => {
    mockExport(200, "emergencies-20260101-000000UTC.csv");
    let downloadName: string | undefined;
    Object.defineProperty(HTMLAnchorElement.prototype, "download", {
      set(value: string) {
        downloadName = value;
      },
      get() {
        return downloadName;
      },
      configurable: true,
    });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    Object.defineProperty(URL, "createObjectURL", {
      value: () => "blob:x",
      configurable: true,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      value: () => undefined,
      configurable: true,
    });

    await exportEmergenciesCsv({});
    expect(downloadName).toBe("emergencies-20260101-000000UTC.csv");
    expect(click).toHaveBeenCalledTimes(1);
  });

  it("throws a catchable ApiError (with message) on a failed export", async () => {
    mockExport(403);
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    await expect(exportEmergenciesCsv({})).rejects.toMatchObject({
      name: "ApiError",
      status: 403,
    });
    expect(click).not.toHaveBeenCalled();
  });
});
