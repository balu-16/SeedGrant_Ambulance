/**
 * Unit tests — components/ui ConfirmDialog: renders the title/body, Escape
 * cancels, confirm fires, and focus is trapped inside the dialog on open
 * (restored to the opener on close).
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Button, ConfirmDialog } from "@/components/ui";

function Harness({
  onConfirm,
  onCancel,
}: {
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <Button
        title="Rotate key"
        onClick={() => {
          setOpen(true);
        }}
      />
      <ConfirmDialog
        open={open}
        title="Rotate API key?"
        body="The old key stops working immediately."
        confirmLabel="Rotate"
        loading={false}
        onConfirm={() => {
          onConfirm();
          setOpen(false);
        }}
        onCancel={() => {
          onCancel();
          setOpen(false);
        }}
      />
    </div>
  );
}

describe("ConfirmDialog", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders title + body inside a modal dialog and confirms", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(<Harness onConfirm={onConfirm} onCancel={onCancel} />);

    await user.click(screen.getByRole("button", { name: "Rotate key" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent(
      "Rotate API key?",
    );
    expect(screen.getByRole("dialog")).toHaveTextContent(
      "The old key stops working immediately.",
    );

    await user.click(screen.getByRole("button", { name: "Rotate" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
    // Focus restored to the element that opened the dialog.
    await waitFor(() => {
      expect(document.activeElement?.textContent).toBe("Rotate key");
    });
  });

  it("Escape cancels and restores focus", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(<Harness onConfirm={onConfirm} onCancel={onCancel} />);

    await user.click(screen.getByRole("button", { name: "Rotate key" }));
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("moves focus into the dialog on open and keeps Tab inside", async () => {
    const user = userEvent.setup();
    render(<Harness onConfirm={() => undefined} onCancel={() => undefined} />);

    await user.click(screen.getByRole("button", { name: "Rotate key" }));
    await screen.findByRole("dialog");
    // First focusable inside the panel (the X close button, then buttons).
    const dialog = screen.getByRole("dialog");
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
    // Tab cycling never leaves the dialog.
    await user.keyboard("{Tab}{Tab}{Tab}{Tab}{Tab}");
    expect(dialog.contains(document.activeElement)).toBe(true);
  });
});
