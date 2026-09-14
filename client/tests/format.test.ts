import { test } from "node:test";
import assert from "node:assert/strict";
import { duration } from "../utils/format";

test("duration buckets seconds, minutes, and hours", () => {
  assert.equal(duration(0, 45_000), "45 sec");
  assert.equal(duration(0, 60_000), "1 min");
  assert.equal(duration(0, 5 * 60_000), "5 min");
  assert.equal(duration(0, 65 * 60_000), "1h 5m");
  assert.equal(duration(0, 120 * 60_000), "2h 0m");
});

test("duration never goes negative", () => {
  assert.equal(duration(10_000, 0), "0 sec");
});
