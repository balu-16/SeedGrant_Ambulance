import {
  Tabs,
  TabList,
  TabSlot,
  TabTrigger,
  type TabTriggerSlotProps,
} from "expo-router/ui";
import { Pressable, StyleSheet } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors as c } from "@/constants/theme";
import { Icon, Txt, type IconName } from "./ui";
function TabButton({
  isFocused,
  children,
  icon,
  ...props
}: TabTriggerSlotProps & { icon: IconName }) {
  return (
    <Pressable
      {...props}
      accessibilityRole="tab"
      accessibilityLabel={typeof children === "string" ? children : undefined}
      accessibilityState={{ selected: isFocused }}
      style={s.tab}
    >
      <Icon name={icon} size={29} color={isFocused ? c.blue : "#8393A9"} />
      <Txt
        style={{
          color: isFocused ? c.blue : c.muted,
          fontSize: 12,
          fontWeight: isFocused ? "600" : "400",
        }}
      >
        {children}
      </Txt>
    </Pressable>
  );
}
export function BottomNavigation() {
  const insets = useSafeAreaInsets();
  return (
    <Tabs style={{ flex: 1 }} options={{ backBehavior: "initialRoute" }}>
      <TabSlot style={{ flex: 1 }} />
      <TabList style={[s.list, { paddingBottom: Math.max(insets.bottom, 8) }]}>
        <TabTrigger name="home" href="/home" asChild>
          <TabButton icon="home">Home</TabButton>
        </TabTrigger>
        <TabTrigger name="history" href="/history" asChild>
          <TabButton icon="history">History</TabButton>
        </TabTrigger>
        <TabTrigger name="profile" href="/profile" asChild>
          <TabButton icon="account">Profile</TabButton>
        </TabTrigger>
      </TabList>
    </Tabs>
  );
}
const s = StyleSheet.create({
  list: {
    backgroundColor: "white",
    borderTopWidth: 1,
    borderColor: c.border,
    paddingTop: 6,
    justifyContent: "space-around",
  },
  tab: {
    alignItems: "center",
    justifyContent: "center",
    gap: 2,
    flex: 1,
    minHeight: 54,
  },
});
