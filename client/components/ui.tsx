import {
  useState,
  type ComponentProps,
  type PropsWithChildren,
  type Ref,
  type ReactNode,
} from "react";
import {
  ActivityIndicator,
  Image,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type RefreshControlProps,
  type StyleProp,
  type TextInputProps,
  type TextStyle,
  type ViewStyle,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { LinearGradient } from "expo-linear-gradient";
import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { colors as c, images, shadow } from "@/constants/theme";

export type IconName = ComponentProps<typeof MaterialCommunityIcons>["name"];
export function Icon({
  name,
  size = 24,
  color = c.blue,
}: {
  name: IconName;
  size?: number;
  color?: string;
}) {
  return (
    <MaterialCommunityIcons
      name={name}
      size={size}
      color={color}
      style={{ lineHeight: size }}
      accessible={false}
      aria-hidden
    />
  );
}
export function Txt({
  children,
  style,
  muted = false,
  ...props
}: PropsWithChildren<{ style?: StyleProp<TextStyle>; muted?: boolean }> &
  ComponentProps<typeof Text>) {
  return (
    <Text {...props} style={[s.text, muted && { color: c.muted }, style]}>
      {children}
    </Text>
  );
}
export function Card({
  children,
  style,
}: PropsWithChildren<{ style?: StyleProp<ViewStyle> }>) {
  return <View style={[s.card, style]}>{children}</View>;
}
export function Badge({
  label,
  tone = "green",
}: {
  label: string;
  tone?: "green" | "blue" | "red" | "muted";
}) {
  const color = c[tone];
  return (
    <View
      style={[
        s.badge,
        {
          backgroundColor:
            tone === "green"
              ? c.greenLight
              : tone === "red"
                ? c.redLight
                : c.blueLight,
        },
      ]}
    >
      <Icon
        name={tone === "green" ? "check-circle" : "circle-small"}
        size={15}
        color={color}
      />
      <Txt
        style={{
          color,
          fontSize: 12,
          lineHeight: 16,
          fontWeight: "600",
          flexShrink: 1,
        }}
      >
        {label}
      </Txt>
    </View>
  );
}
export function IconButton({
  icon,
  label,
  onPress,
  color = c.navy,
}: {
  icon: IconName;
  label: string;
  onPress: () => void;
  color?: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => [s.iconButton, pressed && { opacity: 0.6 }]}
    >
      <Icon name={icon} color={color} />
    </Pressable>
  );
}
export function Button({
  title,
  onPress,
  tone = "blue",
  loading,
  disabled,
  icon = "arrow-right",
  testID,
  edgeIcon = false,
}: {
  title: string;
  onPress: () => void;
  tone?: "blue" | "red" | "quiet";
  loading?: boolean;
  disabled?: boolean;
  icon?: IconName;
  testID?: string;
  edgeIcon?: boolean;
}) {
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={title}
      accessibilityState={{ disabled: disabled || loading, busy: loading }}
      disabled={disabled || loading}
      onPress={onPress}
      style={({ pressed }) => [
        { opacity: disabled || loading ? 0.65 : pressed ? 0.8 : 1 },
        s.buttonShadow,
      ]}
    >
      <LinearGradient
        colors={
          tone === "red"
            ? ["#FF4850", "#EA2632"]
            : tone === "quiet"
              ? [c.blueLight, c.blueLight]
              : ["#4C9AFF", "#1475FF"]
        }
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={s.button}
      >
        {loading ? (
          <ActivityIndicator color="white" />
        ) : (
          <>
            <Txt style={[s.buttonText, tone === "quiet" && { color: c.blue }]}>
              {title}
            </Txt>
            <View
              style={edgeIcon ? { position: "absolute", right: 22 } : undefined}
            >
              <Icon
                name={icon}
                color={tone === "quiet" ? c.blue : "white"}
                size={26}
              />
            </View>
          </>
        )}
      </LinearGradient>
    </Pressable>
  );
}
export function Field({
  label,
  icon,
  error,
  password,
  ...props
}: TextInputProps & {
  label: string;
  icon?: IconName;
  error?: string;
  password?: boolean;
  ref?: Ref<TextInput>;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <View>
      <View style={[s.field, error ? { borderColor: c.red } : null]}>
        {icon && <Icon name={icon} color={c.muted} size={24} />}
        <View style={{ flex: 1 }}>
          <Txt style={s.fieldLabel}>{label}</Txt>
          <TextInput
            {...props}
            accessibilityLabel={label}
            placeholderTextColor="#8A9AB2"
            secureTextEntry={password && !visible}
            style={[s.input, props.style]}
          />
        </View>
        {password && (
          <IconButton
            icon={visible ? "eye-off-outline" : "eye-outline"}
            label={visible ? "Hide password" : "Show password"}
            onPress={() => setVisible(!visible)}
            color={c.muted}
          />
        )}
      </View>
      {error && (
        <Txt accessibilityRole="alert" style={s.error}>
          {error}
        </Txt>
      )}
    </View>
  );
}
export function Page({
  children,
  style,
  refreshControl,
}: PropsWithChildren<{
  style?: StyleProp<ViewStyle>;
  refreshControl?: React.ReactElement<RefreshControlProps>;
}>) {
  return (
    <SafeAreaView edges={["top", "left", "right"]} style={s.safe}>
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={[s.page, style]}
        showsVerticalScrollIndicator={false}
        refreshControl={refreshControl}
      >
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}
export function Avatar({
  size = 40,
  onPress,
}: {
  size?: number;
  onPress?: () => void;
}) {
  const portrait = (
    <Image
      source={images.avatar}
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: "#D5E3EF",
      }}
      accessibilityLabel="Driver avatar"
    />
  );
  return onPress ? (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Open Profile"
      onPress={onPress}
      style={{
        minHeight: 44,
        minWidth: 44,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {portrait}
    </Pressable>
  ) : (
    portrait
  );
}
export function Header({
  title,
  subtitle,
  children,
}: PropsWithChildren<{ title: string; subtitle: string }>) {
  return (
    <View style={s.header}>
      <View style={{ flex: 1 }}>
        <Txt style={s.heading}>{title}</Txt>
        <Txt muted style={{ marginTop: 3, fontSize: 13 }}>
          {subtitle}
        </Txt>
      </View>
      <View style={s.row}>{children}</View>
    </View>
  );
}
export function Sheet({
  visible,
  title,
  onClose,
  children,
}: PropsWithChildren<{
  visible: boolean;
  title: string;
  onClose: () => void;
}>) {
  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        style={s.backdrop}
      >
        <Pressable
          style={StyleSheet.absoluteFill}
          accessibilityLabel="Close dialog"
          onPress={onClose}
        />
        <SafeAreaView edges={["bottom"]} style={s.sheet}>
          <View
            style={[
              s.row,
              {
                justifyContent: "space-between",
                paddingHorizontal: 20,
                paddingTop: 12,
              },
            ]}
          >
            <Txt style={{ fontSize: 21, fontWeight: "700", flex: 1 }}>
              {title}
            </Txt>
            <IconButton icon="close" label="Close dialog" onPress={onClose} />
          </View>
          <ScrollView
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={{ padding: 20, gap: 16 }}
          >
            {children}
          </ScrollView>
        </SafeAreaView>
      </KeyboardAvoidingView>
    </Modal>
  );
}
export function Empty({ title, body }: { title: string; body: string }) {
  return (
    <Card style={{ alignItems: "center", padding: 30, gap: 10 }}>
      <Icon name="clipboard-text-clock-outline" size={42} />
      <Txt style={{ fontWeight: "700", fontSize: 18 }}>{title}</Txt>
      <Txt muted style={{ textAlign: "center" }}>
        {body}
      </Txt>
    </Card>
  );
}
export function Row({
  children,
  style,
}: PropsWithChildren<{ style?: StyleProp<ViewStyle> }>) {
  return <View style={[s.row, style]}>{children}</View>;
}
export function SectionTitle({
  children,
  action,
}: PropsWithChildren<{ action?: ReactNode }>) {
  return (
    <Row style={{ justifyContent: "space-between", marginTop: 5 }}>
      <Txt style={{ fontSize: 19, fontWeight: "700" }}>{children}</Txt>
      {action}
    </Row>
  );
}
const s = StyleSheet.create({
  text: { color: c.navy, fontSize: 14, lineHeight: 20 },
  card: {
    backgroundColor: "white",
    borderRadius: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: "#EBF1FB",
    ...shadow,
  },
  badge: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    gap: 5,
    paddingHorizontal: 9,
    paddingVertical: 3,
    borderRadius: 20,
  },
  iconButton: {
    width: 44,
    height: 44,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  row: { flexDirection: "row", alignItems: "center", gap: 9 },
  buttonShadow: { borderRadius: 17, ...shadow },
  button: {
    minHeight: 56,
    borderRadius: 17,
    paddingHorizontal: 22,
    paddingVertical: 15,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 14,
  },
  buttonText: {
    color: "white",
    fontSize: 20,
    lineHeight: 26,
    fontWeight: "600",
  },
  field: {
    borderWidth: 1,
    borderColor: c.border,
    borderRadius: 12,
    backgroundColor: "white",
    minHeight: 64,
    paddingHorizontal: 14,
    paddingVertical: 9,
    flexDirection: "row",
    gap: 14,
    alignItems: "center",
  },
  fieldLabel: { fontSize: 14, fontWeight: "600", marginBottom: 1 },
  input: {
    fontSize: 13,
    color: c.navy,
    paddingVertical: 4,
    minHeight: 30,
    paddingHorizontal: 0,
  },
  error: { color: c.red, fontSize: 12, marginTop: 5 },
  safe: { flex: 1, backgroundColor: c.pale },
  page: {
    paddingHorizontal: 16,
    paddingTop: 14,
    gap: 12,
    paddingBottom: 28,
    width: "100%",
    maxWidth: 640,
    alignSelf: "center",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 8,
    gap: 6,
    marginBottom: 2,
  },
  heading: {
    fontSize: 26,
    lineHeight: 32,
    fontWeight: "700",
    letterSpacing: -0.6,
  },
  backdrop: {
    flex: 1,
    backgroundColor: "#0A1B4670",
    justifyContent: "flex-end",
    alignItems: "center",
  },
  sheet: {
    backgroundColor: c.pale,
    borderTopLeftRadius: 26,
    borderTopRightRadius: 26,
    maxHeight: "88%",
    width: "100%",
    maxWidth: 640,
  },
});
