import { Redirect } from "expo-router";
import { useApp } from "@/hooks/useApp";
import { launchRoute } from "@/store/reducer";
export default function Index() {
  const { state } = useApp();
  return <Redirect href={launchRoute(state)} />;
}
