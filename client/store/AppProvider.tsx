import {
  createContext,
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState,
  type Dispatch,
  type PropsWithChildren,
} from "react";
import { initialState } from "@/services/defaultState";
import { loadState, saveState } from "@/services/storage";
import type { AppState } from "@/types/models";
import { reducer, type Action } from "./reducer";
export interface AppContextValue {
  state: AppState;
  dispatch: Dispatch<Action>;
  hydrated: boolean;
  storageError: string | null;
  retryStorage: () => void;
  resetLocalData: () => void;
}
export const AppContext = createContext<AppContextValue | null>(null);
export function AppProvider({ children }: PropsWithChildren) {
  const [state, dispatch] = useReducer(reducer, undefined, () =>
    initialState(),
  );
  const [hydrated, setHydrated] = useState(false);
  const [storageError, setStorageError] = useState<string | null>(null);
  // The state right after a hydrate IS the freshly loaded data — skip that
  // first persistence write (resetLocalData persists the fresh state itself).
  const skipNextSave = useRef(false);
  const load = useCallback(() => {
    loadState()
      .then((saved) => {
        skipNextSave.current = true;
        dispatch({ type: "hydrate", state: saved });
        setHydrated(true);
        setStorageError(null);
      })
      .catch(() =>
        setStorageError("Your saved data could not be opened. Please retry."),
      );
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    if (!hydrated) return;
    if (skipNextSave.current) {
      skipNextSave.current = false;
      return;
    }
    saveState(state)
      .then(() => setStorageError(null))
      .catch(() =>
        setStorageError(
          "Changes could not be saved on this device. Tap to retry.",
        ),
      );
  }, [state, hydrated]);
  const retryStorage = () => {
    if (!hydrated) load();
    else
      saveState(state)
        .then(() => setStorageError(null))
        .catch(() =>
          setStorageError(
            "Changes could not be saved on this device. Tap to retry.",
          ),
        );
  };
  const resetLocalData = () => {
    const fresh = initialState();
    skipNextSave.current = true;
    saveState(fresh)
      .then(() => {
        dispatch({ type: "hydrate", state: fresh });
        setHydrated(true);
        setStorageError(null);
      })
      .catch(() =>
        setStorageError("Device storage is unavailable. Please retry."),
      );
  };
  return (
    <AppContext.Provider
      value={{
        state,
        dispatch,
        hydrated,
        storageError,
        retryStorage,
        resetLocalData,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}
