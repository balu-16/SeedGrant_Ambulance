#!/usr/bin/env node
/**
 * Icon-font subsetter (plan §3.4 / contract §9).
 *
 * Material Symbols ships as a ~3.8 MB variable font; the portal only uses a
 * few dozen ligature icons. This script:
 *   1. scans admin/src for icon ligature names (icon="…", name="…" passed to
 *      <Icon> / Button / Field, nav.ts `icon: "…"`, ternaries like
 *      name={cond ? "a" : "b"});
 *   2. runs the `subset-font` package (harfbuzz) over
 *      node_modules/material-symbols/material-symbols-outlined.woff2 keeping
 *      the glyphs AND ligature substitutions for those names;
 *   3. writes admin/src/assets/material-symbols-subset.woff2, which
 *      styles/theme.css serves as the SAME family name ("Material Symbols
 *      Outlined") so the .ms class and ligature mechanism keep working.
 *
 * Run via `npm run icons:subset` (wired into `prebuild`). When a new icon
 * name is added to the app, re-run it — the build does this automatically.
 * If the subset already exists but the toolchain fails, the script keeps the
 * existing file so a build never breaks on a missing font.
 */

import { mkdir, readFile, readdir, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import subsetFont from "subset-font";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const srcDir = path.join(root, "src");
const sourceFont = path.join(
  root,
  "node_modules",
  "material-symbols",
  "material-symbols-outlined.woff2",
);
const outPath = path.join(srcDir, "assets", "material-symbols-subset.woff2");

/** Known-used names the regexes can miss (dynamic strings, safety margin). */
const EXTRA_ICONS = [
  "add", "add_business", "arrow_forward", "badge", "bolt", "call", "casino",
  "check", "check_circle", "chevron_right", "close", "content_copy",
  "dashboard", "dns", "download", "edit_note", "email", "emergency",
  "engineering", "error", "event_available", "event_note", "explore",
  "filter_alt", "group", "hourglass_empty", "key", "local_hospital",
  "local_shipping", "location_on", "lock", "lock_reset", "logout", "mail",
  "map", "memory", "menu", "monitor_heart", "monitoring", "my_location",
  "notes", "notifications_active", "notifications_off", "password",
  "pending_actions", "person_add", "receipt_long", "refresh", "sensors",
  "search", "settings", "terminal", "timer", "traffic", "verified_user",
  "visibility", "visibility_off", "wifi_off",
];

const NAME_RE = /(?:\bicon\b|\bname\b)\s*[:=]\s*"([a-z][a-z_0-9]*)"/g;
const TERNARY_RE = /(?:\bicon\b|\bname\b)\s*=\s*\{([^{}]*)\}/g;
const QUOTED_RE = /"([a-z][a-z_0-9]*)"/g;

async function walk(dir, extensions) {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...(await walk(full, extensions)));
    else if (extensions.has(path.extname(entry.name))) out.push(full);
  }
  return out;
}

async function collectIconNames() {
  const names = new Set(EXTRA_ICONS);
  const files = await walk(srcDir, new Set([".ts", ".tsx"]));
  for (const file of files) {
    const text = await readFile(file, "utf8");
    for (const m of text.matchAll(NAME_RE)) names.add(m[1]);
    for (const m of text.matchAll(TERNARY_RE)) {
      for (const q of m[1].matchAll(QUOTED_RE)) names.add(q[1]);
    }
  }
  // Not icon names: react input name attributes like "email"/"password" are
  // harmless extra glyphs, but drop a few obvious non-ligature collisions.
  names.delete("username");
  names.delete("current-password");
  names.delete("new-password");
  return [...names].sort();
}

async function main() {
  const names = await collectIconNames();
  const font = await readFile(sourceFont);
  // Pin the variable axes to the values the .ms class uses (regular weight,
  // default fill/grade, 24px optical size) — without this the variable-font
  // data dominates and the subset barely shrinks.
  const subset = await subsetFont(font, names.join(""), {
    targetFormat: "woff2",
    variationAxes: { wght: 400, opsz: 24, FILL: 0, GRAD: 0 },
  });
  await mkdir(path.dirname(outPath), { recursive: true });
  await writeFile(outPath, subset);
  const kb = (n) => `${Math.max(1, Math.round(n / 1024))} KB`;
  console.log(
    `subset-icons: ${names.length} ligatures → ${outPath} (${kb(font.length)} → ${kb(subset.length)})`,
  );
}

main().catch((err) => {
  console.error(`subset-icons failed: ${err?.message ?? err}`);
  // Never break the build when a previously generated subset exists.
  stat(outPath)
    .then((s) => {
      if (s.isFile()) {
        console.error("keeping the existing subset — build can proceed");
        process.exit(0);
      }
      process.exit(1);
    })
    .catch(() => process.exit(1));
});
