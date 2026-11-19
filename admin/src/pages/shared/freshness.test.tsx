/**
 * Unit tests — shared/freshness.ts: staleness rules (contract §9) — portal
 * stale threshold, GPS-stale badge rule, observed_at age, and the ticking
 * useFreshness hook rendered through FreshnessCaption.
 */

import { render, screen } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  isGpsStale,
  isStale,
  observedAgeSeconds,
} from "@/pages/shared/freshness";
import { FreshnessCaption } from "@/pages/shared/bits";

describe("isStale (portal freshness)", () => {
  it("is stale only past the threshold", () => {
    const now = 1_000_000_000;
    const updatedAt = now - 10_000; // 10s ago
    expect(isStale(updatedAt, 30, now)).toBe(false);
    expect(isStale(now - 30_000, 30, now)).toBe(false); // exactly 30s → not yet
    expect(isStale(now - 31_000, 30, now)).toBe(true);
  });

  it("is never stale without a successful refresh", () => {
    expect(isStale(undefined, 30, 1_000)).toBe(false);
  });
});

describe("isGpsStale (Stale GPS badge rule)", () => {
  it("requires a fix and applies the gps threshold", () => {
    const now = 1_000_000_000;
    expect(isGpsStale(null, 30, now)).toBe(false);
    expect(isGpsStale(undefined, 30, now)).toBe(false);
    const recent = new Date(now - 10_000).toISOString();
    const old = new Date(now - 60_000).toISOString();
    expect(isGpsStale(recent, 30, now)).toBe(false);
    expect(isGpsStale(old, 30, now)).toBe(true);
    expect(isGpsStale("not-a-date", 30, now)).toBe(false);
  });
});

describe("observedAgeSeconds", () => {
  it("returns null for missing/invalid stamps", () => {
    expect(observedAgeSeconds(null, 1_000)).toBeNull();
    expect(observedAgeSeconds("bogus", 1_000)).toBeNull();
  });

  it("floors the age to seconds", () => {
    const now = 1_000_000_000;
    const observed = new Date(now - 5_500).toISOString();
    expect(observedAgeSeconds(observed, now)).toBe(5);
  });
});

describe("FreshnessCaption", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the age of the last successful update and ticks", () => {
    vi.setSystemTime(new Date("2026-01-01T00:00:05Z"));
    render(<FreshnessCaption updatedAt={Date.now() - 8_000} />);
    expect(screen.getByText(/Last updated/)).toHaveTextContent("8s ago");

    // Ticks with the 1s interval (act wraps the interval callback).
    act(() => {
      vi.advanceTimersByTime(3_000);
    });
    expect(screen.getByText(/Last updated/)).toHaveTextContent("11s ago");
  });

  it("renders a dash without any update", () => {
    render(<FreshnessCaption updatedAt={undefined} />);
    expect(screen.getByText(/Last updated/)).toHaveTextContent("—");
  });
});
