/**
 * Leaflet map wrapper shared by HOSPITAL Live Tracking and POLICE Junction
 * Live (plan §4.2/§4.3). OpenStreetMap tiles, colored L.divIcon dots and a
 * popup per dot. The container gets an explicit height (react-leaflet
 * requirement); the view recenters when the caller's center changes.
 */

import { useEffect } from "react";
import * as L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { DEFAULT_CENTER } from "@/pages/shared/format";

export interface MapDot {
  id: string;
  latitude: number;
  longitude: number;
  /** CSS color of the dot (theme var or hex). */
  color: string;
  /** Popup title (bold first line). */
  title: string;
  /** Optional popup second line. */
  detail?: string;
}

function Recenter({ lat, lng }: { lat: number; lng: number }) {
  const map = useMap();
  useEffect(() => {
    map.setView([lat, lng]);
  }, [lat, lng, map]);
  return null;
}

let iconCache: Map<string, L.DivIcon> | null = null;

function dotIcon(color: string): L.DivIcon {
  if (!iconCache) iconCache = new Map();
  const cached = iconCache.get(color);
  if (cached) return cached;
  const icon = L.divIcon({
    className: "map-dot", // custom class → no default white leaflet box
    html: `<span style="display:block;width:16px;height:16px;border-radius:50%;background:${color};border:2.5px solid var(--white);box-shadow:0 1px 5px rgba(10,27,70,0.45)"></span>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
    popupAnchor: [0, -11],
  });
  iconCache.set(color, icon);
  return icon;
}

export function MapView({
  dots,
  center = DEFAULT_CENTER,
  zoom = 14,
  height = 420,
  ariaLabel,
}: {
  dots: MapDot[];
  center?: [number, number];
  zoom?: number;
  height?: number;
  ariaLabel?: string;
}) {
  return (
    <MapContainer
      center={center}
      zoom={zoom}
      scrollWheelZoom
      style={{
        height,
        width: "100%",
        borderRadius: "var(--radius-card)",
        border: "1px solid var(--card-border)",
        boxShadow: "var(--shadow-card)",
        zIndex: 0,
      }}
      aria-label={ariaLabel}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Recenter lat={center[0]} lng={center[1]} />
      {dots.map((dot) => (
        <Marker
          key={dot.id}
          position={[dot.latitude, dot.longitude]}
          icon={dotIcon(dot.color)}
        >
          <Popup>
            <strong>{dot.title}</strong>
            {dot.detail ? (
              <>
                <br />
                {dot.detail}
              </>
            ) : null}
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
