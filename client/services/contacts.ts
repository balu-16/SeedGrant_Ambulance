/**
 * Emergency contacts API (the driver's trusted contacts, capped at 5).
 *
 * All network calls go through the shared `request()` client (see api.ts) so
 * they inherit auth headers, refresh-on-401, and the common error mapping.
 * The contact picker is permission-free (the OS hands over a single contact)
 * and degrades to `null` everywhere it is unavailable (web, simulator) or
 * cancelled, so callers never need to handle a throw.
 */

import { Platform } from "react-native";
// SDK 57 moved the classic contacts functions behind the `/legacy` entry
// point — importing them from the main package throws at runtime.
import * as Contacts from "expo-contacts/legacy";

import type { EmergencyContact } from "../types/models";

import { request } from "./api";

/** Backend cap for the saved contacts list (the server rejects more). */
export const MAX_CONTACTS = 5;

/**
 * Module-level cache of the saved contacts — lets the SOS prompt in
 * HomeScreen lazily fetch once per app run without prop drilling. Cleared
 * whenever the server list changes (save/delete) so the next read is fresh.
 */
let contactsCache: EmergencyContact[] | null = null;

export async function listContacts(): Promise<EmergencyContact[]> {
  if (contactsCache) return contactsCache;
  const list = await request<EmergencyContact[]>("/contacts");
  contactsCache = list;
  return list;
}

export async function saveContacts(
  contacts: { name: string; phone: string }[],
): Promise<EmergencyContact[]> {
  const saved = await request<EmergencyContact[]>("/contacts", {
    method: "PUT",
    body: { contacts },
  });
  contactsCache = saved;
  return saved;
}

export async function deleteContact(id: string): Promise<{ deleted: boolean }> {
  const result = await request<{ deleted: boolean }>(`/contacts/${id}`, {
    method: "DELETE",
  });
  // The cached list no longer matches the server — drop it.
  contactsCache = null;
  return result;
}

/** Same phone rule the profile editor enforces (see ProfileScreen). */
export function isValidPhone(phone: string): boolean {
  return /^[+\d ()-]{7,20}$/.test(phone);
}

/**
 * Open the OS contact picker and extract the first phone number of the
 * picked contact. Resolves `null` on web, when the picker is unavailable
 * (simulator), when the user cancels, and when the contact has no phone
 * number — `null` always means "nothing to add".
 */
export async function pickContact(): Promise<{
  name: string;
  phone: string;
} | null> {
  if (Platform.OS === "web") return null; // picker is native-only
  try {
    const contact = await Contacts.presentContactPickerAsync();
    if (!contact) return null; // user cancelled
    const name =
      contact.name ??
      [contact.firstName, contact.lastName].filter(Boolean).join(" ");
    const phone = (contact.phoneNumbers?.[0]?.number ?? "").replace(/\s+/g, "");
    if (!phone) return null;
    return { name, phone };
  } catch {
    return null; // picker unavailable (simulator) — treated as cancelled
  }
}
