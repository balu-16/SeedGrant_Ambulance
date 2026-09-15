/**
 * Hermetic mock of the SeedGrant backend for Playwright e2e (node --test-free).
 * Implements the exact subset of /api/v1 the driver app calls, with the same
 * {success, data} envelope and error shape as FastAPI. Starts empty: history
 * grows only from sessions started/stopped through the app.
 *
 * Run: node tests/mock-backend.mjs  (listens on MOCK_PORT or 8787)
 */
import http from "node:http";

const PORT = Number(process.env.MOCK_PORT ?? 8787);

const USER = {
  id: "usr-driver-1",
  email: "driver001@example.com",
  password: "123456",
  role: "DRIVER",
};
const AMBULANCE = {
  id: "amb-1",
  vehicle_no: "KA 01 MJ 5511",
  driver_id: USER.id,
  on_duty: true,
  hospital: {
    id: "hos-1",
    name: "City General Hospital",
    address: "1 Rescue Road",
    latitude: 12.9805,
    longitude: 77.5946,
    phone: "+91 80000 00000",
  },
};
const HOSPITALS = [AMBULANCE.hospital].concat([
  { id: "hos-2", name: "St. Martha's", latitude: 12.975, longitude: 77.6 },
]);
const JUNCTIONS = [
  { id: "jct-1", name: "Trinity Circle", latitude: 12.972, longitude: 77.595 },
  { id: "jct-2", name: "Hosur Road Signal", latitude: 12.97, longitude: 77.6 },
];
const PROFILE = {
  name: "Ravi Kumar",
  phone: "+91 90000 00001",
  region: "Bengaluru",
  hospital: AMBULANCE.hospital.name,
  control_center: "Bengaluru Traffic Control",
};

let accessSeq = 0;
let refreshSeq = 0;
const sessions = new Map(); // session_id -> {status, hospital, started_at, ...}

const ok = (data) => JSON.stringify({ success: true, data });
const fail = (status, code, message) => ({
  status,
  body: JSON.stringify({ success: false, error: { code, message } }),
});

function readBody(req) {
  return new Promise((resolve) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      try {
        resolve(raw ? JSON.parse(raw) : {});
      } catch {
        resolve({});
      }
    });
  });
}

const server = http.createServer(async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader(
    "Access-Control-Allow-Methods",
    "GET,POST,PATCH,PUT,DELETE,OPTIONS",
  );
  res.setHeader("Access-Control-Allow-Headers", "Authorization, Content-Type");
  if (req.method === "OPTIONS") {
    res.writeHead(204).end();
    return;
  }
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const path = url.pathname.replace(/^\/api\/v1/, "");
  if (path === "/healthz") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ success: true, data: { status: "ok" } }));
    return;
  }
  const seg = path.split("/").filter(Boolean);
  const send = (status, body) => {
    res.writeHead(status, { "Content-Type": "application/json" });
    res.end(body);
  };
  const body = await readBody(req);
  const auth = req.headers.authorization ?? "";

  // ---- auth ----
  if (path === "/auth/login" && req.method === "POST") {
    const email = String(body.email ?? "")
      .trim()
      .toLowerCase();
    if (email !== USER.email || body.password !== USER.password) {
      const f = fail(401, "UNAUTHORIZED", "Invalid credentials");
      send(f.status, f.body);
      return;
    }
    send(
      200,
      ok({
        access_token: `mock-access-${++accessSeq}`,
        refresh_token: `mock-refresh-${++refreshSeq}`,
        user: { id: USER.id, email: USER.email, role: USER.role },
      }),
    );
    return;
  }
  if (path === "/auth/refresh" && req.method === "POST") {
    send(
      200,
      ok({
        access_token: `mock-access-${++accessSeq}`,
        refresh_token: `mock-refresh-${++refreshSeq}`,
      }),
    );
    return;
  }
  if (path === "/auth/logout" && req.method === "POST") {
    send(200, ok({ logged_out: true }));
    return;
  }
  if (path === "/auth/me" && req.method === "GET") {
    if (!auth)
      return send(
        fail(401, "UNAUTHORIZED", "No token").status,
        fail(401, "UNAUTHORIZED", "No token").body,
      );
    send(200, ok({ id: USER.id, email: USER.email, role: USER.role }));
    return;
  }
  if (path === "/auth/change-password" && req.method === "POST") {
    send(200, ok({ changed: true }));
    return;
  }
  if (path === "/auth/profile") {
    if (req.method === "GET") {
      send(200, ok({ ...PROFILE }));
      return;
    }
    if (req.method === "PATCH") {
      Object.assign(PROFILE, body);
      send(200, ok({ ...PROFILE }));
      return;
    }
  }

  // ---- driver resources ----
  if (path === "/ambulances/mine" && req.method === "GET") {
    send(200, ok(AMBULANCE));
    return;
  }
  if (path === "/hospitals" && req.method === "GET") {
    send(
      200,
      ok(
        HOSPITALS.map((h) => ({
          id: h.id,
          name: h.name,
          latitude: h.latitude,
          longitude: h.longitude,
        })),
      ),
    );
    return;
  }
  if (path === "/junctions" && req.method === "GET") {
    send(200, ok(JUNCTIONS));
    return;
  }

  // ---- emergency sessions ----
  if (path === "/emergencies/start" && req.method === "POST") {
    const sid = `ses-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
    sessions.set(sid, {
      status: "ACTIVE",
      hospital: body.hospital ?? AMBULANCE.hospital.name,
      started_at: new Date().toISOString(),
    });
    send(200, ok({ session_id: sid, status: "ACTIVE" }));
    return;
  }
  if (seg[0] === "emergencies" && seg[2] === "gps" && req.method === "POST") {
    const s = sessions.get(seg[1]);
    if (!s)
      return send(
        404,
        JSON.stringify({
          success: false,
          error: { code: "NOT_FOUND", message: "Session not found" },
        }),
      );
    send(
      200,
      ok({
        nearby: [
          {
            junction_id: JUNCTIONS[0].id,
            distance_m: 150,
            approach: "NORTH",
            approaching: true,
          },
        ],
        command: null,
        status: s.status,
      }),
    );
    return;
  }
  if (path === "/emergencies/current" && req.method === "GET") {
    const live = [...sessions.entries()].find(([, s]) => s.status === "ACTIVE");
    const latest = [...sessions.entries()].sort(
      ([, a], [, b]) =>
        new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
    )[0];
    send(
      200,
      ok(
        live
          ? { active: true, session_id: live[0], status: live[1].status }
          : latest
            ? { active: false, session_id: latest[0], status: latest[1].status }
            : { active: false },
      ),
    );
    return;
  }
  if (
    seg[0] === "emergencies" &&
    seg[1] &&
    ["stop", "cancel"].includes(seg[2] ?? "") &&
    req.method === "POST"
  ) {
    const s = sessions.get(seg[1]);
    if (s) s.status = seg[2] === "cancel" ? "CANCELLED" : "COMPLETED";
    send(
      200,
      ok({
        status: s ? s.status : "COMPLETED",
        release_sent: true,
        release_pending: false,
      }),
    );
    return;
  }
  if (
    seg[0] === "emergencies" &&
    seg[2] === "heartbeat" &&
    req.method === "POST"
  ) {
    const s = sessions.get(seg[1]);
    send(200, ok({ status: s ? s.status : "ACTIVE" }));
    return;
  }
  if (
    seg[0] === "emergencies" &&
    seg[2] === "patient" &&
    req.method === "POST"
  ) {
    send(200, ok({ status: sessions.get(seg[1])?.status ?? "ACTIVE" }));
    return;
  }
  if (path === "/emergencies/history" && req.method === "GET") {
    send(
      200,
      ok(
        [...sessions.entries()]
          .filter(([, s]) =>
            ["COMPLETED", "CANCELLED", "TIMED_OUT"].includes(s.status),
          )
          .map(([sid, s]) => ({
            id: sid,
            status: s.status,
            hospital: s.hospital,
            ended_reason: s.status,
            started_at: s.started_at,
            ended_at: new Date().toISOString(),
            distance_m: 1200,
            junctions_crossed: 0,
            events: [
              {
                id: `${sid}-start`,
                kind: "session",
                type: "started",
                at: s.started_at,
              },
              {
                id: `${sid}-end`,
                kind: "session",
                type: s.status,
                at: new Date().toISOString(),
              },
            ],
            last_latitude: 12.9716,
            last_longitude: 77.5946,
          })),
      ),
    );
    return;
  }

  // ---- push + contacts ----
  if (path === "/push/register" && req.method === "POST") {
    send(200, ok({ registered: true }));
    return;
  }
  if (seg[0] === "push" && req.method === "DELETE") {
    send(200, ok({ deleted: true }));
    return;
  }
  if (path === "/contacts" && req.method === "GET") {
    send(200, ok([]));
    return;
  }
  if (path === "/contacts" && req.method === "POST") {
    send(200, ok([]));
    return;
  }
  if (seg[0] === "contacts" && req.method === "DELETE") {
    send(200, ok({ deleted: true }));
    return;
  }

  const f = fail(404, "NOT_FOUND", `No mock for ${req.method} ${path}`);
  send(f.status, f.body);
});

server.listen(PORT, () => {
  console.log(`[mock-backend] listening on http://localhost:${PORT}`);
});
