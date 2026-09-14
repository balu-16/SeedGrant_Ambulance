import type { AppState, LocationSnapshot } from "../types/models";

/**
 * Snapshot shown before the first GPS fix arrives. Its zero coordinates are
 * never plotted — LiveRouteMap falls back to the route illustration while
 * coordinates are unusable.
 */
export const EMPTY_LOCATION: LocationSnapshot = {
  latitude: 0,
  longitude: 0,
  area: "Waiting for GPS",
  road: "",
  junction: { id: "", name: "Unknown junction", approach: "North" },
};

/**
 * Real initial state. Identity, vehicle and hospital arrive from the backend
 * (GET /auth/me, GET /ambulances/mine) after sign-in; nothing is seeded
 * locally — there is no offline demo.
 */
export function initialState(): AppState {
  return {
    version: 1,
    onboardingComplete: false,
    auth: null,
    driver: {
      id: "",
      name: "",
      email: "",
      phone: "",
      region: "",
      onDuty: false,
    },
    ambulance: {
      id: "",
      vehicleNumber: "",
      hospital: "",
      controlCenter: "",
    },
    active: null,
    history: [],
    settings: { reducedMotion: false, confirmEmergency: false },
  };
}
