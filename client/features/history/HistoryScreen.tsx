import { useCallback, useState } from "react";
import { Pressable, RefreshControl, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { EventTimeline } from "@/components/EventTimeline";
import {
  Avatar,
  Badge,
  Button,
  Card,
  Empty,
  Field,
  Header,
  Icon,
  IconButton,
  Page,
  Row,
  Sheet,
  Txt,
} from "@/components/ui";
import { colors as c } from "@/constants/theme";
import { useApp } from "@/hooks/useApp";
import {
  backendHistory,
  isBackendLinked,
  mapHistoryItem,
} from "@/services/emergency";
import type { EmergencySession } from "@/types/models";
import { date, duration, time } from "@/utils/format";
import { filterHistory, type Period } from "@/utils/history";
export default function HistoryScreen() {
  const { state } = useApp();
  const router = useRouter();
  const [period, setPeriod] = useState<Period>("All");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState(false);
  const [filter, setFilter] = useState(false);
  const [status, setStatus] = useState<"all" | "completed">("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  // Backend sessions (real API) merge above local history when linked.
  const [remote, setRemote] = useState<EmergencySession[]>([]);
  const [remoteError, setRemoteError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [limit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const loadBackend = useCallback(
    async (nextOffset: number, append: boolean) => {
      if (!(await isBackendLinked())) {
        setRemote(append ? (r) => r : []);
        setRemoteError("");
        return;
      }
      try {
        const rows = await backendHistory({
          limit,
          offset: nextOffset,
          status: status === "completed" ? "COMPLETED" : undefined,
          q: query || undefined,
        });
        const mapped = rows.map(mapHistoryItem);
        setRemote((prev) => (append ? [...prev, ...mapped] : mapped));
        setHasMore(rows.length === limit);
        setOffset(nextOffset);
        setRemoteError("");
      } catch {
        if (!append) setRemoteError("Couldn't load backend sessions.");
      }
    },
    [limit, status, query],
  );
  // Refetch on every focus so newly ended sessions appear without an app
  // restart. A failed fetch keeps the last successful data on screen and
  // surfaces an inline error instead of silently clearing the list.
  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      (async () => {
        if (!cancelled) void loadBackend(0, false);
      })();
      return () => {
        cancelled = true;
      };
    }, [loadBackend]),
  );
  const onRefresh = useCallback(() => {
    setRefreshing(true);
    void loadBackend(0, false).finally(() => setRefreshing(false));
  }, [loadBackend]);
  const all = [...remote, ...state.history];
  const sessions = filterHistory(all, period, query, status);
  const month = filterHistory(all, "This Month", "", "all");
  const completed = month.filter((s) => s.status === "completed");
  // Avg duration counts only finished (terminal) sessions — still-active
  // backend sessions have no meaningful duration yet.
  const terminal = month.filter((s) => s.status !== "active");
  const average = terminal.length
    ? Math.round(
        terminal.reduce(
          (sum, s) => sum + ((s.endedAt ?? s.startedAt) - s.startedAt) / 60000,
          0,
        ) / terminal.length,
      )
    : 0;
  return (
    <Page
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
      }
    >
      <Header title="History" subtitle="Past emergency sessions">
        <IconButton
          icon="magnify"
          label="Search history"
          onPress={() => {
            // Hiding the search field must not leave the query applied
            // invisibly — clear it when search is toggled off.
            if (search) setQuery("");
            setSearch(!search);
          }}
        />
        <IconButton
          icon="filter-variant"
          label="Filter history"
          onPress={() => setFilter(true)}
        />
        <Avatar size={36} onPress={() => router.navigate("/profile")} />
      </Header>
      <Row style={{ gap: 7, alignItems: "stretch" }}>
        {(
          [
            {
              title: "Total Sessions",
              value: month.length,
              note: "This Month",
              icon: "alarm-light",
              color: c.red,
              bg: c.redLight,
            },
            {
              title: "Completed",
              value: completed.length,
              note: `${month.length ? Math.round((completed.length / month.length) * 100) : 0}% Success`,
              icon: "check-circle",
              color: c.green,
              bg: c.greenLight,
            },
            {
              title: "Avg. Duration",
              value: `${average} min`,
              note: "This Month",
              icon: "clock",
              color: c.blue,
              bg: c.blueLight,
            },
          ] as const
        ).map((stat) => (
          <Card
            key={stat.title}
            style={{ flex: 1, padding: 10, gap: 4, borderRadius: 13 }}
          >
            <Row style={{ gap: 5 }}>
              <View
                style={{
                  backgroundColor: stat.bg,
                  padding: 5,
                  borderRadius: 8,
                }}
              >
                <Icon name={stat.icon} size={21} color={stat.color} />
              </View>
              <Txt muted style={{ fontSize: 9, lineHeight: 12, flex: 1 }}>
                {stat.title}
              </Txt>
            </Row>
            <Txt style={{ fontSize: 23, lineHeight: 28, fontWeight: "700" }}>
              {stat.value}
            </Txt>
            <Txt muted style={{ fontSize: 9, lineHeight: 13 }}>
              {stat.note}
            </Txt>
          </Card>
        ))}
      </Row>
      {remoteError ? (
        <Txt accessibilityRole="alert" style={{ color: c.red, fontSize: 11 }}>
          {remoteError}
        </Txt>
      ) : null}
      {search && (
        <Field
          label="Search hospitals"
          icon="magnify"
          placeholder="Hospital name"
          value={query}
          onChangeText={setQuery}
          autoFocus
        />
      )}
      <Row style={{ gap: 7, flexWrap: "wrap", marginVertical: 1 }}>
        {(["All", "Today", "This Week", "This Month"] as const).map((item) => (
          <Pressable
            key={item}
            onPress={() => setPeriod(item)}
            accessibilityRole="button"
            accessibilityState={{ selected: period === item }}
            style={{
              minHeight: 44,
              justifyContent: "center",
              paddingHorizontal: 14,
              backgroundColor: period === item ? c.blue : "#E8F0FC",
              borderRadius: 25,
            }}
          >
            <Txt
              style={{
                color: period === item ? "white" : c.muted,
                fontSize: 12,
              }}
            >
              {item}
            </Txt>
          </Pressable>
        ))}
      </Row>
      {sessions.length === 0 && (
        <Empty
          title="No sessions found"
          body="Try another date range or hospital name. Completed emergencies appear here."
        />
      )}
      {sessions.map((session) => (
        <Card key={session.id} style={{ padding: 13, gap: 6 }}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Emergency session at ${session.hospital}`}
            accessibilityState={{ expanded: expanded === session.id }}
            onPress={() =>
              setExpanded(expanded === session.id ? null : session.id)
            }
          >
            <Row
              style={{
                justifyContent: "space-between",
                flexWrap: "wrap",
                gap: 5,
              }}
            >
              <Txt style={{ fontSize: 12, fontWeight: "700" }}>
                {date(session.startedAt)} · {time(session.startedAt)}
              </Txt>
              <Row style={{ gap: 2 }}>
                <Badge
                  label={
                    session.status === "completed"
                      ? "Completed"
                      : session.status === "cancelled"
                        ? "Cancelled"
                        : "Active"
                  }
                  tone={
                    session.status === "completed"
                      ? "green"
                      : session.status === "cancelled"
                        ? "muted"
                        : "red"
                  }
                />
                <Icon
                  name={
                    expanded === session.id ? "chevron-up" : "chevron-right"
                  }
                  size={18}
                  color={c.muted}
                />
              </Row>
            </Row>
            <Row style={{ marginTop: 11, alignItems: "flex-start", gap: 8 }}>
              <Icon name="map-marker" size={25} color={c.red} />
              <View style={{ flex: 1.5 }}>
                <Txt
                  style={{ fontSize: 12, fontWeight: "700", lineHeight: 17 }}
                >
                  {session.hospital}
                </Txt>
                <Txt muted style={{ fontSize: 10 }}>
                  Distance: {session.distanceKm} km
                </Txt>
              </View>
              <View
                style={{
                  flex: 0.8,
                  borderLeftWidth: 1,
                  borderColor: c.border,
                  paddingLeft: 9,
                }}
              >
                <Txt muted style={{ fontSize: 10 }}>
                  Duration
                </Txt>
                <Txt style={{ fontSize: 12, fontWeight: "700" }}>
                  {session.endedAt
                    ? duration(session.startedAt, session.endedAt)
                    : "—"}
                </Txt>
              </View>
              <View
                style={{
                  flex: 0.8,
                  borderLeftWidth: 1,
                  borderColor: c.border,
                  paddingLeft: 9,
                }}
              >
                <Txt muted style={{ fontSize: 10 }}>
                  Junctions
                </Txt>
                <Txt style={{ fontSize: 12, fontWeight: "700" }}>
                  {session.junctionsCrossed} crossed
                </Txt>
              </View>
            </Row>
          </Pressable>
          <EventTimeline
            events={session.events}
            expanded={expanded === session.id}
          />
        </Card>
      ))}
      {hasMore && (
        <Button
          title="Load more"
          tone="quiet"
          onPress={() => void loadBackend(offset + limit, true)}
        />
      )}
      <Sheet
        visible={filter}
        title="Filter History"
        onClose={() => setFilter(false)}
      >
        <Txt muted>Completion status</Txt>
        {(["all", "completed"] as const).map((value) => (
          <Pressable
            key={value}
            accessibilityRole="radio"
            accessibilityState={{ checked: status === value }}
            onPress={() => {
              setStatus(value);
              setFilter(false);
            }}
          >
            <Card>
              <Row>
                <Icon
                  name={status === value ? "radiobox-marked" : "radiobox-blank"}
                />
                <Txt>
                  {value === "all" ? "All sessions" : "Completed sessions"}
                </Txt>
              </Row>
            </Card>
          </Pressable>
        ))}
      </Sheet>
    </Page>
  );
}
