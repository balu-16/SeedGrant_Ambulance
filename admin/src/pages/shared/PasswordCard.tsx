/**
 * Change-password card shared by HOSPITAL and POLICE Settings (plan §4.2/§4.3
 * Settings). POST /auth/change-password via services/portal.changePassword;
 * success/error are inline — never alert(). Other sessions are signed out by
 * the server on success.
 */

import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { changePassword } from "@/services/portal";
import { Button, Field, Icon, Txt } from "@/components/ui";
import { InlineError } from "@/pages/shared/bits";

const MIN_LENGTH = 8;

export function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [changed, setChanged] = useState(false);

  const mutation = useMutation({
    mutationFn: () => changePassword(current, next),
    onSuccess: () => {
      setChanged(true);
      setCurrent("");
      setNext("");
      setConfirm("");
    },
    onError: (err) => {
      setChanged(false);
      setError(
        err instanceof Error ? err.message : "Could not change password.",
      );
    },
  });

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setChanged(false);
    setError(null);
    if (!current || !next || !confirm) {
      setError("Fill in your current password and the new password twice.");
      return;
    }
    if (next.length < MIN_LENGTH) {
      setError(`New password must be at least ${MIN_LENGTH} characters.`);
      return;
    }
    if (next !== confirm) {
      setError("New password and confirmation do not match.");
      return;
    }
    if (next === current) {
      setError("The new password must differ from the current one.");
      return;
    }
    mutation.mutate();
  };

  return (
    <form
      className="card"
      style={{ display: "flex", flexDirection: "column", gap: 14 }}
      onSubmit={onSubmit}
      noValidate
    >
      <Txt as="h2" style={{ fontSize: 19, lineHeight: 26, fontWeight: 700 }}>
        Change Password
      </Txt>
      <Field
        label="Current password"
        icon="lock"
        password
        autoComplete="current-password"
        placeholder="Enter your current password"
        value={current}
        onChange={(e) => setCurrent(e.target.value)}
      />
      <Field
        label="New password"
        icon="lock_reset"
        password
        autoComplete="new-password"
        placeholder={`At least ${MIN_LENGTH} characters`}
        value={next}
        onChange={(e) => setNext(e.target.value)}
      />
      <Field
        label="Confirm new password"
        icon="lock_reset"
        password
        autoComplete="new-password"
        placeholder="Repeat the new password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
      />

      {changed && (
        <div
          role="status"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            color: "var(--green)",
            fontSize: 13,
            lineHeight: 18,
            background: "var(--green-light)",
            borderRadius: 12,
            padding: "10px 12px",
          }}
        >
          <Icon name="check_circle" size={18} color="var(--green)" />
          <span>password changed — other sessions signed out</span>
        </div>
      )}
      {error && <InlineError error={error} />}

      <Button
        type="submit"
        title="Change password"
        icon="check"
        block
        loading={mutation.isPending}
      />
    </form>
  );
}
