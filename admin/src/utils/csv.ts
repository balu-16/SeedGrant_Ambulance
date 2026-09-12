/**
 * Client-side CSV export (plan §4.2 — HOSPITAL emergencies CSV for
 * records/insurance). Builds the file from already-loaded rows: RFC-4180
 * quoting, Excel-friendly BOM, Blob + a.download. No server round-trip.
 */

const NEEDS_QUOTES = /[",\n\r]/;

function csvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  const raw =
    value instanceof Date
      ? value.toISOString()
      : typeof value === "object"
        ? JSON.stringify(value)
        : String(value);
  return NEEDS_QUOTES.test(raw) ? `"${raw.replace(/"/g, '""')}"` : raw;
}

/**
 * Download `rows` as `filename.csv`. The header is the union of every row's
 * keys (first-seen order); missing cells become empty strings.
 */
export function downloadCsv(
  filename: string,
  rows: Record<string, unknown>[],
): void {
  const headers = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  const lines = [
    headers.map(csvCell).join(","),
    ...rows.map((row) => headers.map((h) => csvCell(row[h])).join(",")),
  ];
  // BOM so Excel opens the file as UTF-8.
  const blob = new Blob(["\uFEFF" + lines.join("\r\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
