import { View } from "react-native";
import type { EventKind, PriorityEvent } from "@/types/models";
import { colors as c } from "@/constants/theme";
import { time } from "@/utils/format";
import { Icon, Row, Txt, type IconName } from "./ui";
const eventInfo: Record<
  EventKind,
  { label: string; icon: IconName; color: string }
> = {
  started: { label: "Emergency Started", icon: "play", color: c.red },
  requested: { label: "Priority Requested", icon: "broadcast", color: c.green },
  granted: {
    label: "Green Priority Granted",
    icon: "traffic-light",
    color: c.green,
  },
  released: {
    label: "Priority Released",
    icon: "transit-connection-variant",
    color: c.blue,
  },
  crossed: { label: "Junction Crossed", icon: "check", color: c.blue },
  ended: { label: "Emergency Ended", icon: "flag", color: c.green },
};
export function EventTimeline({
  events,
  expanded = false,
}: {
  events: PriorityEvent[];
  expanded?: boolean;
}) {
  const preview = events.filter((e) =>
    ["started", "requested", "released", "ended"].includes(e.kind),
  );
  const shown = expanded
    ? events
    : [
        preview[0],
        preview.find((e) => e.kind === "requested"),
        [...preview].reverse().find((e) => e.kind === "released"),
        preview.find((e) => e.kind === "ended"),
      ].filter((e): e is PriorityEvent => !!e);
  return (
    <View
      style={{
        flexDirection: expanded ? "column" : "row",
        gap: expanded ? 14 : 5,
        marginTop: 10,
      }}
    >
      {shown.map((e) => {
        const info = eventInfo[e.kind];
        return expanded ? (
          <Row key={e.id}>
            <View
              style={{
                backgroundColor: info.color,
                borderRadius: 18,
                padding: 6,
              }}
            >
              <Icon name={info.icon} color="white" size={18} />
            </View>
            <View style={{ flex: 1 }}>
              <Txt style={{ fontWeight: "600" }}>{info.label}</Txt>
              {e.junction && (
                <Txt muted style={{ fontSize: 12 }}>
                  {e.junction}
                </Txt>
              )}
            </View>
            <Txt muted style={{ fontSize: 12 }}>
              {time(e.timestamp)}
            </Txt>
          </Row>
        ) : (
          <View key={e.id} style={{ flex: 1 }}>
            <Row style={{ gap: 4 }}>
              <View
                style={{
                  backgroundColor: info.color,
                  borderRadius: 15,
                  padding: 4,
                }}
              >
                <Icon name={info.icon} size={15} color="white" />
              </View>
              <View style={{ flex: 1, height: 1, backgroundColor: c.border }} />
            </Row>
            <Txt style={{ fontSize: 10, marginTop: 4, lineHeight: 14 }}>
              {time(e.timestamp)}
            </Txt>
            <Txt muted style={{ fontSize: 10, lineHeight: 14 }}>
              {info.label}
            </Txt>
          </View>
        );
      })}
    </View>
  );
}
