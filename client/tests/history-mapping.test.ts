import { test } from "node:test";
import assert from "node:assert/strict";
import { mapHistoryItem } from "../services/emergency";
import type { BackendHistoryItem } from "../services/emergency";

const base: BackendHistoryItem = {
  id: "abc-123",
  status: "COMPLETED",
  hospital: "City General",
  ended_reason: null,
  started_at: "2026-09-12T10:00:00Z",
  ended_at: "2026-09-12T10:05:00Z",
};

test("completed backend rows map to completed with a real end time", () => {
  const s = mapHistoryItem(base);
  assert.equal(s.status, "completed");
  assert.equal(s.endedAt, Date.parse("2026-09-12T10:05:00Z"));
  assert.equal(s.hospital, "City General");
  assert.ok(s.id.startsWith("backend-"));
});

test("active backend rows stay active with no fake end time", () => {
  const s = mapHistoryItem({ ...base, status: "CROSSING", ended_at: null });
  assert.equal(s.status, "active");
  assert.equal(s.endedAt, undefined);
});

test("cancelled and timed-out rows keep distinct terminal statuses", () => {
  assert.equal(
    mapHistoryItem({ ...base, status: "CANCELLED" }).status,
    "cancelled",
  );
  assert.equal(
    mapHistoryItem({ ...base, status: "TIMED_OUT" }).status,
    "timed_out",
  );
});

test("a missing hospital falls back to the display default", () => {
  assert.equal(
    mapHistoryItem({ ...base, hospital: null }).hospital,
    "Unnamed hospital",
  );
});
