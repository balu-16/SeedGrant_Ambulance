export interface Driver {
  id: string;
  name: string;
  email: string;
  phone: string;
  region: string;
  onDuty: boolean;
}
export interface Ambulance {
  id: string;
  vehicleNumber: string;
  hospital: string;
  controlCenter: string;
}
export interface EmergencyContact {
  id: string;
  name: string;
  phone: string;
}
export interface MockSession {
  driverId: string;
  signedInAt: number;
}
export interface Junction {
  id: string;
  name: string;
  approach: "East" | "North" | "West" | "South";
}
export interface LocationSnapshot {
  latitude: number;
  longitude: number;
  area: string;
  road: string;
  junction: Junction;
}
export type EventKind =
  "started" | "requested" | "granted" | "released" | "crossed" | "ended";
export interface PriorityEvent {
  id: string;
  kind: EventKind;
  timestamp: number;
  junction?: string;
  approach?: string;
}
export interface EmergencySession {
  id: string;
  startedAt: number;
  endedAt?: number;
  hospital: string;
  distanceKm: number;
  status: "active" | "completed" | "cancelled";
  junctionsCrossed: number;
  events: PriorityEvent[];
  priority: "standby" | "requested" | "granted" | "released";
  location: LocationSnapshot;
}
export interface Settings {
  reducedMotion: boolean;
  confirmEmergency: boolean;
}
export interface AppState {
  version: 1;
  onboardingComplete: boolean;
  auth: MockSession | null;
  driver: Driver;
  ambulance: Ambulance;
  active: EmergencySession | null;
  history: EmergencySession[];
  settings: Settings;
}
