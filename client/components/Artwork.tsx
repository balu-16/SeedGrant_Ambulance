import Svg, { Circle, Path, Rect, G } from "react-native-svg";
import { colors as c } from "@/constants/theme";
export function AmbulanceMark({
  size = 64,
  white = false,
}: {
  size?: number;
  white?: boolean;
}) {
  return (
    <Svg
      width={size}
      height={size * 0.72}
      viewBox="0 0 100 72"
      accessibilityLabel="Ambulance"
    >
      <Path
        d="M10 27 Q10 20 18 20 H65 L85 37 Q94 37 94 46 V58 H9Z"
        fill="white"
      />
      <Path d="M66 24 H73 L84 37 H66Z" fill={white ? "#FFD3D6" : c.red} />
      <Rect
        x="38"
        y="25"
        width="9"
        height="25"
        fill={white ? "#FF8B92" : c.red}
      />
      <Rect
        x="30"
        y="33"
        width="25"
        height="9"
        fill={white ? "#FF8B92" : c.red}
      />
      <Rect
        x="48"
        y="12"
        width="16"
        height="6"
        rx="3"
        fill={white ? "white" : c.red}
      />
      <Path
        d="M55 2 V7 M39 5 L44 10 M71 5 L66 10"
        stroke={white ? "white" : c.red}
        strokeWidth="3"
        strokeLinecap="round"
      />
      <Circle cx="27" cy="58" r="10" fill={white ? "white" : c.navy} />
      <Circle cx="77" cy="58" r="10" fill={white ? "white" : c.navy} />
      <Circle cx="27" cy="58" r="5" fill={white ? c.red : "white"} />
      <Circle cx="77" cy="58" r="5" fill={white ? c.red : "white"} />
    </Svg>
  );
}
export function Heartbeat({ width = 100 }: { width?: number }) {
  return (
    <Svg width={width} height={44} viewBox="0 0 140 50">
      <Path
        d="M0 27 H45 L52 20 L60 35 L70 3 L80 47 L89 21 L96 27 H140"
        stroke="#C4D9F4"
        strokeWidth="2.4"
        fill="none"
      />
    </Svg>
  );
}
export function RouteMap({
  active = false,
  large = false,
}: {
  active?: boolean;
  large?: boolean;
}) {
  return (
    <Svg
      width="100%"
      height={large ? 230 : 110}
      viewBox="0 0 300 160"
      preserveAspectRatio="xMidYMid slice"
      accessibilityLabel="Illustrated offline route to hospital"
    >
      <Rect width="300" height="160" fill="#F0F4F8" />
      {[20, 70, 120, 170, 220, 270].map((x) => (
        <G key={x}>
          <Rect
            x={x}
            y="12"
            width="31"
            height="38"
            fill={x % 40 ? "#DCF1E7" : "#F8EFDA"}
          />
          <Rect x={x} y="105" width="33" height="48" fill="#DDF1E6" />
          <Path d={`M${x} 0 L${x - 45} 160`} stroke="white" strokeWidth="9" />
        </G>
      ))}
      {[30, 70, 110, 145].map((y) => (
        <Path
          key={y}
          d={`M0 ${y} L300 ${y - 35}`}
          stroke="white"
          strokeWidth="8"
        />
      ))}
      <Path
        d="M65 137 C84 85 112 142 142 86 S196 90 236 32"
        fill="none"
        stroke="#B5D5FF"
        strokeWidth="13"
      />
      <Path
        d="M65 137 C84 85 112 142 142 86 S196 90 236 32"
        fill="none"
        stroke={active ? c.blue : "#6DA8FB"}
        strokeWidth="6"
      />
      <Circle cx="65" cy="137" r="15" fill="white" />
      <Path d="M65 125 L56 143 L65 139 L74 143Z" fill={c.blue} />
      <Path
        d="M236 10 C213 10 217 34 236 48 C255 34 259 10 236 10"
        fill={c.red}
      />
      <Path
        d="M231 20 V31 M241 20 V31 M231 25 H241"
        stroke="white"
        strokeWidth="3"
      />
    </Svg>
  );
}
