/**
 * ADMIN Users (plan §4.1) — portal account management: create users
 * (ADMIN/HOSPITAL/POLICE/DRIVER with hospital/junction scoping), enable or
 * disable accounts, and reset passwords (generated password shown exactly
 * once, with copy).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import {
  createUser,
  listHospitals,
  listJunctions,
  listUsers,
  patchUser,
  resetUserPassword,
} from "@/services/portal";
import type { PortalUser } from "@/types/portal";
import {
  Badge,
  Button,
  Card,
  Drawer,
  Empty,
  Field,
  PageHeader,
  Row,
  Table,
  Txt,
  type TableColumn,
} from "@/components/ui";
import {
  errMsg,
  fmtDate,
  generatePassword,
  roleTone,
  shortId,
} from "@/pages/admin/shared";
import {
  CheckRow,
  ErrorCard,
  LoadingBlock,
  MiniButton,
  SelectField,
} from "@/pages/admin/widgets";
import "@/pages/admin/admin.css";

const ROLES = ["ADMIN", "HOSPITAL", "POLICE", "DRIVER"];

export function UsersPage() {
  const qc = useQueryClient();
  const users = useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => listUsers({ limit: 200 }),
  });
  const hospitals = useQuery({
    queryKey: ["admin", "hospitals"],
    queryFn: listHospitals,
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [resetUser, setResetUser] = useState<PortalUser | null>(null);

  const toggleM = useMutation({
    mutationFn: (u: PortalUser) => patchUser(u.id, { is_active: !u.is_active }),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });

  const roleM = useMutation({
    mutationFn: ({ id, role }: { id: string; role: string }) =>
      patchUser(id, { role }),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });

  const hospitalNames = new Map(
    (hospitals.data ?? []).map((h) => [h.id, h.name]),
  );

  const columns: TableColumn<PortalUser>[] = [
    { key: "email", header: "Email", render: (u) => u.email },
    {
      key: "role",
      header: "Role",
      render: (u) => (
        <select
          aria-label={`Role for ${u.email}`}
          className="admin-select"
          value={u.role}
          disabled={roleM.isPending}
          onChange={(e) => {
            const role = e.target.value;
            if (role !== u.role) roleM.mutate({ id: u.id, role });
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      ),
    },
    {
      key: "is_active",
      header: "Active",
      render: (u) => (
        <Row>
          <Badge
            label={u.is_active ? "Active" : "Disabled"}
            tone={u.is_active ? "green" : "red"}
          />
          <MiniButton
            title={u.is_active ? "Disable" : "Enable"}
            loading={toggleM.isPending && toggleM.variables?.id === u.id}
            onClick={() => toggleM.mutate(u)}
          />
        </Row>
      ),
    },
    {
      key: "hospital",
      header: "Hospital",
      render: (u) =>
        u.hospital_id ? (hospitalNames.get(u.hospital_id) ?? shortId(u.hospital_id)) : "—",
    },
    {
      key: "junctions",
      header: "Junctions",
      render: (u) => (u.junction_ids.length > 0 ? u.junction_ids.length : "—"),
    },
    { key: "created", header: "Created", render: (u) => fmtDate(u.created_at) },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (u) => (
        <MiniButton title="Reset password" onClick={() => setResetUser(u)} />
      ),
    },
  ];

  return (
    <div className="page-body">
      <PageHeader
        title="Users"
        subtitle="Portal accounts, roles and scope assignments"
      >
        <Button title="New user" icon="person_add" onClick={() => setCreateOpen(true)} />
      </PageHeader>

      {toggleM.isError && (
        <ErrorCard
          title="Could not update the user"
          error={toggleM.error}
          onRetry={() => toggleM.reset()}
        />
      )}

      {users.isError ? (
        <ErrorCard
          title="Could not load users"
          error={users.error}
          onRetry={() => void users.refetch()}
        />
      ) : users.isLoading ? (
        <LoadingBlock label="Loading users" />
      ) : (
        <Table
          columns={columns}
          rows={users.data?.items ?? []}
          keyOf={(u) => u.id}
          emptyFallback={
            <Empty
              icon="group"
              title="No users yet"
              body="Create ADMIN, HOSPITAL, POLICE or DRIVER portal accounts here."
            />
          }
        />
      )}

      <CreateUserDrawer open={createOpen} onClose={() => setCreateOpen(false)} />
      <ResetPasswordDrawer
        user={resetUser}
        onClose={() => setResetUser(null)}
      />
    </div>
  );
}

function CreateUserDrawer({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const hospitals = useQuery({
    queryKey: ["admin", "hospitals"],
    queryFn: listHospitals,
  });
  const junctions = useQuery({
    queryKey: ["admin", "junctions"],
    queryFn: listJunctions,
  });

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("DRIVER");
  const [hospitalId, setHospitalId] = useState("");
  const [junctionIds, setJunctionIds] = useState<string[]>([]);
  const [formErr, setFormErr] = useState<string | null>(null);

  const createM = useMutation({
    mutationFn: () =>
      createUser({
        email: email.trim(),
        password,
        role,
        ...(role === "HOSPITAL" && hospitalId ? { hospital_id: hospitalId } : {}),
        ...(role === "POLICE" ? { junction_ids: junctionIds } : {}),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin", "users"] });
      close();
    },
    onError: (e) => setFormErr(errMsg(e)),
  });

  function close() {
    onClose();
    setEmail("");
    setPassword("");
    setRole("DRIVER");
    setHospitalId("");
    setJunctionIds([]);
    setFormErr(null);
  }

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormErr(null);
    if (!email.includes("@")) {
      setFormErr("Enter a valid email address.");
      return;
    }
    if (password.length < 8) {
      setFormErr("Password must be at least 8 characters.");
      return;
    }
    if (role === "HOSPITAL" && !hospitalId) {
      setFormErr("Select a hospital for this user.");
      return;
    }
    if (role === "POLICE" && junctionIds.length === 0) {
      setFormErr("Assign at least one junction to this officer.");
      return;
    }
    createM.mutate();
  }

  return (
    <Drawer open={open} title="New user" onClose={close} width={460}>
      <form
        onSubmit={submit}
        style={{ display: "flex", flexDirection: "column", gap: 14 }}
      >
        <Field
          label="Email"
          icon="mail"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="user@example.com"
        />

        <div>
          <Field
            label="Password"
            icon="lock"
            password
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Min 8 characters"
          />
          <Row style={{ marginTop: 8 }}>
            <MiniButton
              title="Generate password"
              icon="casino"
              onClick={() => setPassword(generatePassword())}
            />
          </Row>
        </div>

        <SelectField label="Role" value={role} onChange={setRole}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </SelectField>

        {role === "HOSPITAL" && (
          <SelectField
            label="Hospital"
            value={hospitalId}
            onChange={setHospitalId}
          >
            <option value="">— Select hospital —</option>
            {(hospitals.data ?? []).map((h) => (
              <option key={h.id} value={h.id}>
                {h.name}
              </option>
            ))}
          </SelectField>
        )}

        {role === "POLICE" && (
          <div>
            <Txt as="div" className="field-label" style={{ marginBottom: 6 }}>
              Junctions
            </Txt>
            <div className="admin-check-grid">
              {(junctions.data ?? []).map((j) => (
                <CheckRow
                  key={j.id}
                  label={j.name}
                  checked={junctionIds.includes(j.id)}
                  onChange={(c) =>
                    setJunctionIds((ids) =>
                      c ? [...ids, j.id] : ids.filter((x) => x !== j.id),
                    )
                  }
                />
              ))}
            </div>
          </div>
        )}

        {formErr && (
          <div className="admin-inline-error" role="alert">
            {formErr}
          </div>
        )}

        <Button
          type="submit"
          title="Create user"
          block
          loading={createM.isPending}
        />
      </form>
    </Drawer>
  );
}

function ResetPasswordDrawer({
  user,
  onClose,
}: {
  user: PortalUser | null;
  onClose: () => void;
}) {
  return (
    <Drawer
      open={user !== null}
      title="Reset password"
      onClose={onClose}
      width={430}
    >
      {user && <ResetBody key={user.id} user={user} />}
    </Drawer>
  );
}

function ResetBody({ user }: { user: PortalUser }) {
  const [generated, setGenerated] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () => resetUserPassword(user.id),
    onSuccess: (res) => {
      setGenerated(res.password);
      setCopied(false);
    },
    onError: (e) => setErr(errMsg(e)),
  });

  async function copy() {
    if (!generated) return;
    try {
      await navigator.clipboard.writeText(generated);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return !generated ? (
        <>
          <Txt>
            Generate a new password for <b>{user.email}</b>. Their current
            password stops working immediately.
          </Txt>
          {err && (
            <div className="admin-inline-error" role="alert">
              {err}
            </div>
          )}
          <Button
            title="Generate & reset"
            icon="key"
            block
            loading={m.isPending}
            onClick={() => m.mutate()}
          />
        </>
      ) : (
        <>
          <Card style={{ background: "var(--navy)" }}>
            <Txt
              as="div"
              style={{
                color: "rgba(255,255,255,.6)",
                fontSize: 12,
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: 0.4,
              }}
            >
              New password — shown only once
            </Txt>
            <Txt
              as="div"
              className="admin-mono"
              style={{
                color: "var(--white)",
                fontSize: 20,
                marginTop: 8,
                wordBreak: "break-all",
              }}
            >
              {generated}
            </Txt>
          </Card>
          <Row>
            <Button
              title={copied ? "Copied" : "Copy password"}
              icon={copied ? "check" : "content_copy"}
              onClick={() => void copy()}
            />
          </Row>
          <Txt muted>
            Copy it now and share it with the user over a secure channel —
            this password will never be shown again.
          </Txt>
        </>
      );
}
