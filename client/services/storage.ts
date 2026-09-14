import AsyncStorage from "@react-native-async-storage/async-storage";
import type { AppState } from "../types/models";
import { initialState } from "./defaultState";
import { decodeState } from "../utils/persistence";
// v2 key: old v1 storage held seeded demo sessions/profile — ignored, not migrated.
export const STORAGE_KEY = "ambulance-driver:v2";
// Writes are ordered so an older write cannot overwrite a later logout.
let writeQueue: Promise<void> = Promise.resolve();
export function saveState(state: AppState): Promise<void> {
  const json = JSON.stringify(state);
  const operation = writeQueue
    .catch(() => undefined)
    .then(() => AsyncStorage.setItem(STORAGE_KEY, json));
  writeQueue = operation;
  return operation;
}
export async function loadState(): Promise<AppState> {
  const raw = await AsyncStorage.getItem(STORAGE_KEY);
  if (!raw) return initialState();
  return decodeState(raw);
}
