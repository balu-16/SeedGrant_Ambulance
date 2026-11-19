/**
 * Leaflet map wrapper shared by HOSPITAL Live Tracking and POLICE Junction
 * Live (plan §4.2/§4.3). OpenStreetMap tiles, colored L.divIcon dots and a
 * popup per dot. The container gets an explicit height (react-leaflet
 * requirement); the view recenters when the caller's center changes.
 *
 * Tile failures (plan §3.4 "keep maps usable when external tile loading
 * fails"): TileLayerGuard listens for tileerror and renders a dismissible
 * overlay message — markers, popups and the caller's list stay usable.
 */

import { useEffect, useState } from "react";
import * as L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { DEFAULT_CENTER, tileUrl } from "@/pages/shared/format";
import { Icon } from "@/components/ui";

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

/**
 * TileLayer + in-map fallback banner when tiles cannot load (offline dev,
 * blocked CDN). Map interaction continues; the caller's list is unaffected.
 */
export function TileLayerGuard({
  attribution,
  url,
}: {
  attribution: string;
  url: string;
}) {
  const [tilesFailed, setTilesFailed] = useState(false);
  return (
    <>
      <TileLayer
        attribution={attribution}
        url={url}
        eventHandlers={{ tileerror: () => setTilesFailed(true) }}
      />
      {tilesFailed && (
        <div className="map-tile-fallback" role="status">
          <Icon name="map" size={18} color="var(--heading)" />
          <span>
            Map tiles could not be loaded — markers stay visible and the
            session list remains available.
          </span>
        </div>
      )}
    </>
  );
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
      <TileLayerGuard attribution="&copy; <a href='https://www.openstreetmap.org/copyright' target='_blank' rel='noreferrer'>OpenStreetMap</a> contributors" url={tileUrl()} />
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
