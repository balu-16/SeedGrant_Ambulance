import { useEffect, useState } from "react";
import { Linking, Pressable, StyleSheet, Switch, View } from "react-native";
import { AmbulanceMark, Heartbeat } from "@/components/Artwork";
import {
  Avatar,
  Badge,
  Button,
  Card,
  Field,
  Header,
  Icon,
  IconButton,
  Page,
  Row,
  SectionTitle,
  Sheet,
  Txt,
  type IconName,
} from "@/components/ui";
import { colors as c } from "@/constants/theme";
import { SUPPORT_EMAIL, SUPPORT_PHONE } from "@/constants/support";
import { useApp } from "@/hooks/useApp";
import {
  apiChangePassword,
  apiGetProfile,
  apiLogout,
  apiMe,
  apiMyAmbulance,
  apiUpdateProfile,
  isBackendLinked,
} from "@/services/api";
import {
  deleteContact,
  isValidPhone,
  listContacts,
  MAX_CONTACTS,
  pickContact,
  saveContacts,
} from "@/services/contacts";
import {
  backendCurrent,
  retrackBackendSession,
  stopActiveBackendSession,
} from "@/services/emergency";
import { unregisterTokenFromBackend } from "@/services/notifications";
import type { Ambulance, Driver, EmergencyContact } from "@/types/models";
type Dialog =
  | "driver"
  | "ambulance"
  | "settings"
  | "password"
  | "help"
  | "logout"
  | "contacts"
  | null;
/** Backend account row — visible only when logged in against the real API. */
function BackendAccount() {
  const [info, setInfo] = useState<{
    email: string;
    role: string;
    vehicle: string;
    name: string;
    phone: string;
  } | null>(null);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!(await isBackendLinked())) return;
      try {
        const me = await apiMe();
        let vehicle = "—";
        try {
          vehicle = (await apiMyAmbulance()).vehicle_no;
        } catch {
          vehicle = "unassigned";
        }
        let name = "";
        let phone = "";
        try {
          const prof = await apiGetProfile();
          name = prof.name;
          phone = prof.phone;
        } catch {
          /* profile row missing — email/vehicle still shown */
        }
        if (!cancelled)
          setInfo({ email: me.email, role: me.role, vehicle, name, phone });
      } catch {
        if (!cancelled) setInfo(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);
  if (!info) return null;
  return (
    <Card style={{ gap: 8, padding: 12 }}>
      <SectionTitle>
        <Icon name="server" /> Backend Account
      </SectionTitle>
      <Detail icon="email" label="Login Email" value={info.email} />
      {info.phone ? (
        <Detail icon="phone" label="Phone" value={info.phone} />
      ) : null}
      <Detail icon="shield-account" label="Role" value={info.role} />
      <Detail icon="car" label="Assigned Vehicle" value={info.vehicle} />
    </Card>
  );
}
function Detail({
  icon,
  label,
  value,
}: {
  icon: IconName;
  label: string;
  value: string;
}) {
  return (
    <Row style={{ gap: 10, alignItems: "flex-start" }}>
      <Icon name={icon} size={18} color={c.muted} />
      <Txt muted style={{ flex: 1, fontSize: 11 }}>
        {label}
      </Txt>
      <Txt style={{ flex: 1.25, fontSize: 12 }}>{value}</Txt>
    </Row>
  );
}
function SettingRow({
  icon,
  title,
  onPress,
  red,
}: {
  icon: IconName;
  title: string;
  onPress: () => void;
  red?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={[
        s.settingRow,
        red && {
          backgroundColor: c.redLight,
          borderRadius: 9,
          borderBottomWidth: 0,
          paddingHorizontal: 10,
        },
      ]}
    >
      <Icon name={icon} size={22} color={red ? c.red : c.muted} />
      <Txt style={{ flex: 1, color: red ? c.red : c.navy, fontSize: 13 }}>
        {title}
      </Txt>
      <Icon name="chevron-right" color={red ? c.red : c.muted} size={21} />
    </Pressable>
  );
}
function ProfileEditor({
  kind,
  onClose,
}: {
  kind: "driver" | "ambulance";
  onClose: () => void;
}) {
  const { state, dispatch } = useApp();
  const [driver, setDriver] = useState<Driver>({ ...state.driver });
  const [ambulance, setAmbulance] = useState<Ambulance>({ ...state.ambulance });
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  /** Sync local edits to the backend profile; surfaces errors inline. */
  function syncBackendProfile(patch: {
    name: string;
    phone: string;
    region: string;
    hospital: string;
    control_center: string;
  }) {
    // The server's ProfileIn replaces every field, so send the full known
    // set (driver + ambulance halves) instead of a partial patch.
    setSaved("");
    void isBackendLinked()
      .then((linked) => (linked ? apiUpdateProfile(patch) : undefined))
      .then((res) => {
        if (res) setSaved("Saved to control center.");
      })
      .catch((e: unknown) =>
        setError(
          e instanceof Error ? e.message : "Sync failed. Local copy kept.",
        ),
      );
  }
  function save() {
    if (kind === "driver") {
      if (
        !driver.name.trim() ||
        !driver.region.trim() ||
        !/^\S+@\S+\.\S+$/.test(driver.email.trim()) ||
        !/^[+\d ()-]{7,20}$/.test(driver.phone.trim())
      ) {
        setError("Enter a name, region, valid email, and phone number.");
        return;
      }
      dispatch({
        type: "driver",
        patch: {
          name: driver.name.trim(),
          email: driver.email.trim(),
          phone: driver.phone.trim(),
          region: driver.region.trim(),
        },
      });
      syncBackendProfile({
        name: driver.name.trim(),
        phone: driver.phone.trim(),
        region: driver.region.trim(),
        hospital: state.ambulance.hospital,
        control_center: state.ambulance.controlCenter,
      });
    } else {
      if (
        ![
          ambulance.vehicleNumber,
          ambulance.hospital,
          ambulance.controlCenter,
        ].every((v) => v.trim())
      ) {
        setError("Please complete all ambulance details.");
        return;
      }
      dispatch({
        type: "ambulance",
        patch: {
          vehicleNumber: ambulance.vehicleNumber.trim(),
          hospital: ambulance.hospital.trim(),
          controlCenter: ambulance.controlCenter.trim(),
        },
      });
      syncBackendProfile({
        name: state.driver.name,
        phone: state.driver.phone,
        region: state.driver.region,
        hospital: ambulance.hospital.trim(),
        control_center: ambulance.controlCenter.trim(),
      });
    }
    onClose();
  }
  return (
    <>
      <Txt muted>
        Changes save on this device and sync to the control center when
        backend-linked.
      </Txt>
      {kind === "driver" ? (
        <>
          <Field
            label="Full name"
            value={driver.name}
            maxLength={60}
            onChangeText={(name) => setDriver({ ...driver, name })}
          />
          <Field
            label="Email address"
            value={driver.email}
            keyboardType="email-address"
            autoCapitalize="none"
            maxLength={120}
            onChangeText={(email) => setDriver({ ...driver, email })}
          />
          <Field
            label="Phone number"
            value={driver.phone}
            keyboardType="phone-pad"
            maxLength={20}
            onChangeText={(phone) => setDriver({ ...driver, phone })}
          />
          <Field
            label="Assigned region"
            value={driver.region}
            maxLength={100}
            onChangeText={(region) => setDriver({ ...driver, region })}
          />
        </>
      ) : (
        <>
          <Field
            label="Vehicle number"
            value={ambulance.vehicleNumber}
            maxLength={30}
            onChangeText={(vehicleNumber) =>
              setAmbulance({ ...ambulance, vehicleNumber })
            }
          />
          <Field
            label="Assigned hospital"
            value={ambulance.hospital}
            maxLength={100}
            onChangeText={(hospital) =>
              setAmbulance({ ...ambulance, hospital })
            }
          />
          <Field
            label="Control center"
            value={ambulance.controlCenter}
            maxLength={100}
            onChangeText={(controlCenter) =>
              setAmbulance({ ...ambulance, controlCenter })
            }
          />
        </>
      )}
      {error && (
        <Txt accessibilityRole="alert" style={{ color: c.red }}>
          {error}
        </Txt>
      )}
      {saved && <Txt style={{ color: c.green }}>{saved}</Txt>}
      <Button title="Save Changes" icon="check" onPress={save} />
      <Button title="Cancel" tone="quiet" icon="close" onPress={onClose} />
    </>
  );
}
/** Draft editor for the saved emergency contacts (max 5, backend-synced). */
function ContactsEditor({
  initial,
  onSaved,
  onClose,
}: {
  initial: EmergencyContact[];
  onSaved: (contacts: EmergencyContact[]) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<EmergencyContact[]>([...initial]);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  /** Append the contact picked from the device address book to the draft. */
  function addPicked() {
    setError("");
    setSaved("");
    void pickContact()
      .then((picked) => {
        if (!picked) return; // cancelled / unavailable / no phone number
        if (draft.length >= MAX_CONTACTS) {
          setError(`Up to ${MAX_CONTACTS} contacts.`);
          return;
        }
        setDraft([
          ...draft,
          {
            id: `draft-${Date.now()}`,
            name: picked.name,
            phone: picked.phone,
          },
        ]);
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Could not open contacts."),
      );
  }
  /** Append the manually typed contact to the draft. */
  function addManual() {
    setError("");
    setSaved("");
    if (!name.trim() || !isValidPhone(phone.trim())) {
      setError("Enter a name and a valid phone number.");
      return;
    }
    if (draft.length >= MAX_CONTACTS) {
      setError(`Up to ${MAX_CONTACTS} contacts.`);
      return;
    }
    setDraft([
      ...draft,
      { id: `draft-${Date.now()}`, name: name.trim(), phone: phone.trim() },
    ]);
    setName("");
    setPhone("");
  }
  function save() {
    setError("");
    setSaved("");
    void saveContacts(
      draft.map((contact) => ({ name: contact.name, phone: contact.phone })),
    )
      .then((savedList) => {
        setSaved("Saved to control center.");
        onSaved(savedList);
        onClose();
      })
      .catch((e: unknown) =>
        setError(
          e instanceof Error ? e.message : "Saving failed. Local copy kept.",
        ),
      );
  }
  return (
    <>
      {draft.length === 0 ? (
        <Txt muted>No contacts yet — add one below.</Txt>
      ) : (
        draft.map((contact) => (
          <View key={contact.id} style={s.settingRow}>
            <Icon name="account" size={22} color={c.muted} />
            <View style={{ flex: 1 }}>
              <Txt style={{ fontSize: 13 }}>{contact.name}</Txt>
              <Txt muted style={{ fontSize: 11 }}>
                {contact.phone}
              </Txt>
            </View>
            <IconButton
              icon="close"
              label={`Remove ${contact.name}`}
              color={c.muted}
              onPress={() =>
                setDraft(draft.filter((ct) => ct.id !== contact.id))
              }
            />
          </View>
        ))
      )}
      <Txt muted style={{ fontSize: 11 }}>
        {draft.length} / {MAX_CONTACTS} contacts
      </Txt>
      <Button
        title="Pick from Contacts"
        tone="quiet"
        icon="account-plus"
        onPress={addPicked}
        disabled={draft.length >= MAX_CONTACTS}
      />
      <Field label="Name" value={name} maxLength={60} onChangeText={setName} />
      <Field
        label="Phone"
        value={phone}
        keyboardType="phone-pad"
        maxLength={20}
        onChangeText={setPhone}
      />
      <Button
        title="Add"
        tone="quiet"
        icon="plus"
        onPress={addManual}
        disabled={draft.length >= MAX_CONTACTS}
      />
      {error && (
        <Txt accessibilityRole="alert" style={{ color: c.red }}>
          {error}
        </Txt>
      )}
      {saved && <Txt style={{ color: c.green }}>{saved}</Txt>}
      <Button
        title="Save Contacts"
        icon="check"
        onPress={save}
        disabled={draft.length > MAX_CONTACTS}
      />
      <Button title="Cancel" tone="quiet" icon="close" onPress={onClose} />
    </>
  );
}
export default function ProfileScreen() {
  const { state, dispatch } = useApp();
  const { driver, ambulance } = state;
  const [dialog, setDialog] = useState<Dialog>(null);
  const [pwCurrent, setPwCurrent] = useState("");
  const [pwNext, setPwNext] = useState("");
  const [pwMsg, setPwMsg] = useState("");
  const [logoutError, setLogoutError] = useState("");
  // Saved emergency contacts — null until loaded from the backend, so the
  // card stays invisible when the contacts backend is unreachable.
  const [contacts, setContacts] = useState<EmergencyContact[] | null>(null);
  // Hydrate identity from backend truth when linked.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!(await isBackendLinked())) return;
      try {
        const [me, amb] = await Promise.all([
          apiMe(),
          apiMyAmbulance().catch(() => null),
        ]);
        let prof: {
          name: string;
          phone: string;
          region: string;
          hospital: string;
          control_center: string;
        } | null = null;
        try {
          prof = await apiGetProfile();
        } catch {
          prof = null;
        }
        if (cancelled) return;
        if (prof) {
          if (prof.name)
            dispatch({ type: "driver", patch: { name: prof.name } });
          if (prof.phone)
            dispatch({ type: "driver", patch: { phone: prof.phone } });
          if (prof.region)
            dispatch({ type: "driver", patch: { region: prof.region } });
          if (prof.hospital || prof.control_center)
            dispatch({
              type: "ambulance",
              patch: {
                hospital: prof.hospital || ambulance.hospital,
                controlCenter: prof.control_center || ambulance.controlCenter,
              },
            });
        }
        dispatch({ type: "driver", patch: { email: me.email } });
        if (amb)
          dispatch({
            type: "ambulance",
            patch: { vehicleNumber: amb.vehicle_no },
          });
      } catch {
        /* offline — local copy stays */
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // Load emergency contacts once when backend-linked (silent catch — the
  // feature is invisible offline).
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!(await isBackendLinked())) return;
      try {
        const list = await listContacts();
        if (!cancelled) setContacts(list);
      } catch {
        /* offline — emergency contacts stay hidden */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);
  const titles = {
    driver: "Edit Driver Details",
    ambulance: "Edit Ambulance Details",
    settings: "App Settings",
    password: "Change Password",
    help: "Help & Support",
    logout: "Logout",
    contacts: "Emergency Contacts",
  };
  /** Delete one saved contact on the backend, then drop it from the card. */
  function removeContact(id: string) {
    void deleteContact(id)
      .then(() =>
        setContacts((cur) =>
          cur ? cur.filter((contact) => contact.id !== id) : cur,
        ),
      )
      .catch(() => undefined);
  }
  async function logout() {
    // End the backend emergency session (if any) BEFORE revoking tokens so
    // the server-side session never outlives the login. Keep the user signed
    // in when release publication is still pending.
    setLogoutError("");
    let backendLookupFailed = false;
    if (state.active?.backendSessionId) {
      retrackBackendSession(state.active.backendSessionId);
    } else if (await isBackendLinked()) {
      // Profile can be opened directly after a cold launch, before HomeScreen
      // has had a chance to reconcile the persisted backend session id.
      await backendCurrent().catch(() => {
        backendLookupFailed = true;
      });
    }
    if (backendLookupFailed && state.active) {
      setLogoutError(
        "Cannot verify the emergency session. Reconnect and retry.",
      );
      return;
    }
    if (!(await stopActiveBackendSession())) {
      setLogoutError(
        "Backend release is still pending. Retry after reconnecting.",
      );
      return;
    }
    try {
      await unregisterTokenFromBackend().catch(() => false);
      await apiLogout().catch(() => undefined);
    } finally {
      dispatch({ type: "logout", now: Date.now() });
      setDialog(null);
    }
  }
  return (
    <Page>
      <Header
        title="Profile"
        subtitle="Manage your account and vehicle details"
      >
        <IconButton
          icon="help-circle-outline"
          label="Help and support"
          onPress={() => setDialog("help")}
        />
      </Header>
      <View style={s.banner}>
        <Avatar size={80} />
        <View style={{ flex: 1, gap: 3 }}>
          <Txt style={{ fontSize: 22, lineHeight: 27, fontWeight: "700" }}>
            {driver.name}
          </Txt>
          <Txt style={{ fontSize: 13, lineHeight: 17 }}>Ambulance Driver</Txt>
          <Txt muted style={{ fontSize: 11, lineHeight: 16 }}>
            Account ID: {driver.id}
          </Txt>
          <Badge label="Verified Driver" />
        </View>
        <View style={s.bannerArt}>
          <AmbulanceMark size={50} />
          <Heartbeat width={60} />
        </View>
      </View>
      <BackendAccount />
      <Card style={{ gap: 8, padding: 12 }}>
        <SectionTitle
          action={
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Edit driver details"
              onPress={() => setDialog("driver")}
              style={s.edit}
            >
              <Icon name="pencil" size={17} color="#4A6C9A" />
              <Txt style={s.editText}>Edit</Txt>
            </Pressable>
          }
        >
          <Icon name="account" /> Driver Details
        </SectionTitle>
        <Detail icon="phone" label="Phone Number" value={driver.phone} />
        <Detail icon="email" label="Email Address" value={driver.email} />
        <Detail
          icon="map-marker"
          label="Assigned Region"
          value={driver.region}
        />
        <Row>
          <Icon
            name="circle"
            size={14}
            color={driver.onDuty ? c.green : c.muted}
          />
          <Txt muted style={{ flex: 1, fontSize: 11 }}>
            Emergency Duty Status
          </Txt>
          <Switch
            accessibilityLabel="On duty"
            value={driver.onDuty}
            onValueChange={(onDuty) =>
              dispatch({ type: "driver", patch: { onDuty } })
            }
            trackColor={{ true: c.green }}
          />
          <Badge
            label={driver.onDuty ? "On Duty" : "Off Duty"}
            tone={driver.onDuty ? "green" : "muted"}
          />
        </Row>
      </Card>
      <Card style={{ gap: 8, padding: 12 }}>
        <SectionTitle
          action={
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Edit ambulance details"
              onPress={() => setDialog("ambulance")}
              style={s.edit}
            >
              <Icon name="pencil" size={17} color="#4A6C9A" />
              <Txt style={s.editText}>Edit</Txt>
            </Pressable>
          }
        >
          <Icon name="ambulance" color={c.red} /> Ambulance Details
        </SectionTitle>
        <Detail
          icon="car"
          label="Vehicle Number"
          value={ambulance.vehicleNumber}
        />
        <Detail icon="card-text" label="Ambulance ID" value={ambulance.id} />
        <Detail
          icon="hospital-building"
          label="Assigned Hospital"
          value={ambulance.hospital}
        />
        <Detail
          icon="broadcast"
          label="Control Center"
          value={ambulance.controlCenter}
        />
      </Card>
      {contacts !== null && (
        <Card style={{ gap: 8, padding: 12 }}>
          <SectionTitle>
            <Icon name="account-group" /> Emergency Contacts
          </SectionTitle>
          {contacts.map((contact) => (
            <View key={contact.id} style={s.settingRow}>
              <Icon name="account" size={22} color={c.muted} />
              <View style={{ flex: 1 }}>
                <Txt style={{ fontSize: 13 }}>{contact.name}</Txt>
                <Txt muted style={{ fontSize: 11 }}>
                  {contact.phone}
                </Txt>
              </View>
              <IconButton
                icon="close"
                label={`Remove ${contact.name}`}
                color={c.muted}
                onPress={() => removeContact(contact.id)}
              />
            </View>
          ))}
          <Txt muted style={{ fontSize: 11 }}>
            Up to {MAX_CONTACTS} contacts
          </Txt>
          <Button
            title="Add Contact"
            tone="quiet"
            icon="account-plus"
            onPress={() => setDialog("contacts")}
          />
        </Card>
      )}
      <Card>
        <SectionTitle>
          <Icon name="cog" color={c.purple} /> Account Settings
        </SectionTitle>
        <View style={{ marginTop: 8 }}>
          <SettingRow
            icon="pencil"
            title="Edit Profile"
            onPress={() => setDialog("driver")}
          />
          <SettingRow
            icon="lock"
            title="Change Password"
            onPress={() => setDialog("password")}
          />
          <SettingRow
            icon="cog"
            title="App Settings"
            onPress={() => setDialog("settings")}
          />
          <SettingRow
            icon="help-circle"
            title="Help & Support"
            onPress={() => setDialog("help")}
          />
          <SettingRow
            icon="logout"
            title="Logout"
            red
            onPress={() => (state.active ? setDialog("logout") : logout())}
          />
        </View>
      </Card>
      <Sheet
        visible={dialog !== null}
        title={dialog ? titles[dialog] : ""}
        onClose={() => setDialog(null)}
      >
        {(dialog === "driver" || dialog === "ambulance") && (
          <ProfileEditor
            key={dialog}
            kind={dialog}
            onClose={() => setDialog(null)}
          />
        )}
        {dialog === "settings" && (
          <>
            <Row>
              <View style={{ flex: 1 }}>
                <Txt style={{ fontWeight: "600" }}>Reduced motion</Txt>
                <Txt muted>Use instant screen and page transitions.</Txt>
              </View>
              <Switch
                accessibilityLabel="Reduced motion"
                value={state.settings.reducedMotion}
                onValueChange={(reducedMotion) =>
                  dispatch({ type: "settings", patch: { reducedMotion } })
                }
                trackColor={{ true: c.blue }}
              />
            </Row>
            <Row>
              <View style={{ flex: 1 }}>
                <Txt style={{ fontWeight: "600" }}>Emergency confirmations</Txt>
                <Txt muted>Confirm before starting or stopping.</Txt>
              </View>
              <Switch
                accessibilityLabel="Emergency confirmations"
                value={state.settings.confirmEmergency}
                onValueChange={(confirmEmergency) =>
                  dispatch({ type: "settings", patch: { confirmEmergency } })
                }
                trackColor={{ true: c.blue }}
              />
            </Row>
          </>
        )}
        {dialog === "password" && (
          <>
            <Icon name="shield-lock-outline" size={45} />
            <Txt>Change the password on your backend account.</Txt>
            <Field
              label="Current password"
              value={pwCurrent}
              onChangeText={setPwCurrent}
              password
            />
            <Field
              label="New password"
              value={pwNext}
              onChangeText={setPwNext}
              password
            />
            {pwMsg ? <Txt muted>{pwMsg}</Txt> : null}
            <Button
              title="Change Password"
              onPress={() => {
                if (!pwCurrent) {
                  setPwMsg("Enter your current password.");
                  return;
                }
                if (pwNext.length < 8) {
                  setPwMsg("New password must be at least 8 characters.");
                  return;
                }
                if (pwNext === pwCurrent) {
                  setPwMsg("New password must differ from the current one.");
                  return;
                }
                setPwMsg("");
                void apiChangePassword(pwCurrent, pwNext)
                  .then(() => {
                    setPwMsg("Password changed.");
                    setPwCurrent("");
                    setPwNext("");
                  })
                  .catch((e: unknown) =>
                    setPwMsg(e instanceof Error ? e.message : "Change failed."),
                  );
              }}
            />
            <Txt muted>
              Forgot your password? Ask your hospital administrator for a reset
              (Admin → Users → Reset password).
            </Txt>
          </>
        )}
        {dialog === "contacts" && (
          <ContactsEditor
            initial={contacts ?? []}
            onSaved={setContacts}
            onClose={() => setDialog(null)}
          />
        )}
        {dialog === "help" && (
          <>
            <Txt style={{ fontWeight: "700" }}>Every Second Counts</Txt>
            <Txt muted>
              For account or ambulance assignment changes, contact your hospital
              administrator.
            </Txt>
            {SUPPORT_PHONE ? (
              <Button
                title="Call Support"
                tone="quiet"
                onPress={() => void Linking.openURL(`tel:${SUPPORT_PHONE}`)}
              />
            ) : null}
            {SUPPORT_EMAIL ? (
              <Button
                title="Email Support"
                tone="quiet"
                onPress={() => void Linking.openURL(`mailto:${SUPPORT_EMAIL}`)}
              />
            ) : null}
            {!SUPPORT_PHONE && !SUPPORT_EMAIL ? (
              <Txt muted>
                Support contacts are not configured in this build.
              </Txt>
            ) : null}
          </>
        )}
        {dialog === "logout" && (
          <>
            {logoutError ? (
              <Txt accessibilityRole="alert" style={{ color: c.red }}>
                {logoutError}
              </Txt>
            ) : null}
            <Txt>
              An emergency is active. Logging out will end it, release priority,
              and save it to History.
            </Txt>
            <Button
              title="End Emergency & Logout"
              tone="red"
              icon="logout"
              onPress={logout}
            />
            <Button
              title="Cancel"
              tone="quiet"
              icon="close"
              onPress={() => setDialog(null)}
            />
          </>
        )}
      </Sheet>
    </Page>
  );
}
const s = StyleSheet.create({
  banner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 15,
    backgroundColor: "#E6F1FF",
    borderRadius: 16,
    padding: 16,
    minHeight: 120,
    overflow: "hidden",
  },
  bannerArt: { position: "absolute", right: 9, bottom: 7, opacity: 0.25 },
  edit: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    paddingHorizontal: 10,
    minHeight: 36,
    borderRadius: 10,
    backgroundColor: c.blueLight,
  },
  editText: { color: "#4A6C9A", fontSize: 12 },
  settingRow: {
    minHeight: 46,
    flexDirection: "row",
    alignItems: "center",
    gap: 15,
    borderBottomWidth: 1,
    borderColor: c.border,
  },
});
