/**
 * Live free map (react-native-maps + Carto/OSM UrlTile, no API key).
 * Falls back to the static RouteMap illustration on web or when there are
 * no usable coordinates / native maps are unavailable.
 */

import { useMemo } from "react";
import { Platform, StyleSheet, View } from "react-native";
import { RouteMap } from "@/components/Artwork";
import { tilesUrl, type LatLon } from "@/services/routing";

let NativeMaps: typeof import("react-native-maps") | null = null;
if (Platform.OS !== "web") {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    NativeMaps = require("react-native-maps");
  } catch {
    NativeMaps = null;
  }
}

function usable(p: LatLon | null | undefined): boolean {
  return (
    !!p &&
    Number.isFinite(p.latitude) &&
    Number.isFinite(p.longitude) &&
    !(p.latitude === 0 && p.longitude === 0)
  );
}

export function LiveRouteMap({
  origin,
  destination,
  route,
  height = 110,
  active = false,
}: {
  origin: LatLon | null | undefined;
  destination: LatLon | null | undefined;
  /** OSRM polyline; straight line used when empty. */
  route?: LatLon[];
  height?: number;
  active?: boolean;
}) {
  const fallback = useMemo(
    () => <RouteMap active={active} large={height > 160} />,
    [active, height],
  );
  if (Platform.OS === "web" || !NativeMaps) return fallback;
  if (!usable(origin) && !usable(destination)) return fallback;

  const { MapView, UrlTile, Marker, Polyline } = NativeMaps as unknown as {
    MapView: React.ComponentType<Record<string, unknown>>;
    UrlTile: React.ComponentType<Record<string, unknown>>;
    Marker: React.ComponentType<Record<string, unknown>>;
    Polyline: React.ComponentType<Record<string, unknown>>;
  };
  const line: LatLon[] =
    route && route.length >= 2
      ? route
      : [origin, destination].filter((p): p is LatLon => usable(p));
  if (line.length === 0) return fallback;

  const mid = line[Math.floor(line.length / 2)];
  const region = {
    latitude: mid.latitude,
    longitude: mid.longitude,
    latitudeDelta: 0.03,
    longitudeDelta: 0.03,
  };

  return (
    <View
      style={[s.wrap, { height }]}
      accessibilityLabel="Live route to hospital"
    >
      <MapView style={s.map} initialRegion={region}>
        <UrlTile
          urlTemplate={tilesUrl()}
          maximumZ={19}
          flipY={false}
          tileSize={256}
        />
        {line.length >= 2 && (
          <Polyline
            coordinates={line}
            strokeWidth={4}
            strokeColor={active ? "#1475FF" : "#6DA8FB"}
          />
        )}
        {usable(origin) && (
          <Marker coordinate={origin!} pinColor="#1475FF" title="Ambulance" />
        )}
        {usable(destination) && (
          <Marker
            coordinate={destination!}
            pinColor="#E4232D"
            title="Hospital"
          />
        )}
      </MapView>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { width: "100%", overflow: "hidden" },
  map: { width: "100%", height: "100%" },
});
