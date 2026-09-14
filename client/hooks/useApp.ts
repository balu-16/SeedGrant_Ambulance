import { useContext } from "react";
import { AppContext } from "@/store/AppProvider";
export function useApp() {
  const app = useContext(AppContext);
  if (!app) throw new Error("AppProvider is required");
  return app;
}
