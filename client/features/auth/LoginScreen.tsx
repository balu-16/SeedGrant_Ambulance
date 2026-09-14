import { useRef, useState } from "react";
import {
  Image,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  View,
  useWindowDimensions,
  TextInput,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { AmbulanceMark, Heartbeat } from "@/components/Artwork";
import { Button, Field, Icon, Row, Txt } from "@/components/ui";
import { colors as c, images } from "@/constants/theme";
import { useApp } from "@/hooks/useApp";
import { authService } from "@/services/auth";
export default function LoginScreen() {
  const { width: ww } = useWindowDimensions();
  const width = Math.min(ww, 600);
  const { dispatch } = useApp();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const pending = useRef(false);
  const passwordRef = useRef<TextInput>(null);
  async function login() {
    setSubmitted(true);
    setError("");
    if (!identifier.trim() || !password || pending.current) return;
    pending.current = true;
    setLoading(true);
    try {
      const auth = await authService.signIn(identifier, password);
      dispatch({ type: "login", auth });
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Unable to sign in. Please retry.",
      );
    } finally {
      pending.current = false;
      setLoading(false);
    }
  }
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: "#F8FBFF" }}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
      >
        <ScrollView
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
          contentContainerStyle={{
            width,
            alignSelf: "center",
            paddingBottom: 14,
          }}
        >
          <View style={s.hero}>
            <View style={s.logo}>
              <AmbulanceMark size={65} />
            </View>
            <Txt style={s.title}>Driver Login</Txt>
            <Txt muted style={s.subtitle}>
              Emergency traffic priority system
            </Txt>
            <Txt style={s.intro}>
              Access your driver account to receive{"\n"}traffic signal priority
              for emergency routes.
            </Txt>
            <View
              style={{
                width,
                height: width * 0.4,
                marginTop: -5,
                overflow: "hidden",
              }}
            >
              <Image
                source={images.login}
                style={[
                  StyleSheet.absoluteFill,
                  { width: "120%", height: "120%", left: "-12%", top: "-20%" },
                ]}
                resizeMode="cover"
                accessibilityLabel="Ambulance driving through a green signal"
              />
              <Txt style={s.handwritten}>
                Faster roads{"\n"}for a safer{"\n"}tomorrow
              </Txt>
            </View>
          </View>
          <View style={s.panel}>
            <Field
              label="Driver ID / Email"
              icon="email-outline"
              placeholder="Enter your driver ID or email"
              value={identifier}
              onChangeText={setIdentifier}
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="next"
              onSubmitEditing={() => passwordRef.current?.focus()}
              error={
                submitted && !identifier.trim()
                  ? "Enter your driver ID or email."
                  : undefined
              }
            />
            <Field
              ref={passwordRef}
              label="Password"
              icon="lock"
              placeholder="Enter your password"
              value={password}
              onChangeText={setPassword}
              password
              autoCorrect={false}
              autoCapitalize="none"
              returnKeyType="go"
              onSubmitEditing={login}
              error={
                submitted && !password ? "Enter your password." : undefined
              }
            />
            {error ? (
              <Txt
                accessibilityRole="alert"
                style={{ color: c.red, fontSize: 13 }}
              >
                {error}
              </Txt>
            ) : null}
            <Button title="Login" loading={loading} onPress={login} />
            <Row style={s.info}>
              <View style={s.shield}>
                <Icon name="shield-check" size={29} />
              </View>
              <View style={{ flex: 1 }}>
                <Txt style={{ fontWeight: "500", fontSize: 13 }}>
                  Credentials are provided by your hospital administrator.
                </Txt>
                <Txt
                  muted
                  style={{ fontSize: 11, lineHeight: 16, marginTop: 4 }}
                >
                  Drivers are managed by hospital and police admins through the
                  central dashboard.
                </Txt>
              </View>
            </Row>
            <Row style={{ marginTop: 5 }}>
              <View style={s.rule} />
              <Txt muted style={{ fontSize: 11 }}>
                Need help? Contact your hospital admin.
              </Txt>
              <View style={s.rule} />
            </Row>
            <View style={s.footer}>
              <Txt style={{ color: "#8A9FC0", fontSize: 10, letterSpacing: 3 }}>
                Every Second Counts
              </Txt>
              <Heartbeat width={130} />
              <Txt style={{ color: "#8A9FC0", fontSize: 8, letterSpacing: 2 }}>
                SAFE ROADS. HEALTHY LIVES.
              </Txt>
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
const s = StyleSheet.create({
  hero: { alignItems: "center", paddingTop: 18 },
  logo: {
    width: 80,
    height: 80,
    borderRadius: 21,
    backgroundColor: "#E3EEFF",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 12,
  },
  title: {
    fontSize: 27,
    lineHeight: 34,
    fontWeight: "700",
    letterSpacing: -0.4,
  },
  subtitle: { fontSize: 14, marginTop: 2 },
  intro: {
    fontSize: 12,
    lineHeight: 17,
    textAlign: "center",
    marginTop: 15,
    color: "#405C87",
    zIndex: 1,
  },
  handwritten: {
    position: "absolute",
    left: 22,
    top: 17,
    fontStyle: "italic",
    fontSize: 12,
    lineHeight: 16,
    color: "#34567E",
    transform: [{ rotate: "-8deg" }],
  },
  panel: {
    padding: 18,
    gap: 10,
    backgroundColor: "#FFFFFFF2",
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    marginTop: -3,
  },
  info: {
    backgroundColor: "#EFF6FF",
    borderRadius: 14,
    padding: 14,
    gap: 13,
    marginTop: 6,
    alignItems: "flex-start",
  },
  shield: {
    width: 44,
    height: 44,
    borderRadius: 24,
    backgroundColor: "#D8E9FF",
    alignItems: "center",
    justifyContent: "center",
  },
  rule: { flex: 1, height: 1, backgroundColor: "#D9E3F2" },
  footer: { alignItems: "center", paddingTop: 21, gap: 0 },
});
