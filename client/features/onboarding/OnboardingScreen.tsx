import { useRef, useState } from "react";
import {
  FlatList,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
  useWindowDimensions,
} from "react-native";
import {
  SafeAreaView,
  useSafeAreaInsets,
} from "react-native-safe-area-context";
import { LinearGradient } from "expo-linear-gradient";
import { Button, Icon, Row, Txt } from "@/components/ui";
import { colors as c, images, shadow } from "@/constants/theme";
import { useApp } from "@/hooks/useApp";
const slides = [
  {
    image: images.emergency,
    eyebrow: "Every\nSecond\nCounts",
    note: "Clearer roads.\nBrighter tomorrows.",
    title: "Start Emergency",
    accent: "in Seconds",
    body: "When a patient is in the ambulance,\nstart traffic priority quickly.",
  },
  {
    image: images.location,
    eyebrow: "Live\nLocation\nAlways On",
    note: "Together for\nfaster, safer\njourneys.",
    title: "Stay on Route",
    accent: "Save Lives",
    body: "Your live location helps our control center\ntrack the ambulance and guide\ntraffic priority.",
  },
  {
    image: images.priority,
    eyebrow: "Smarter\nJunctions\nSafer Lives",
    note: "Connected signals.\nFaster response.",
    title: "Faster Green Routes",
    accent: "When It Matters",
    body: "Traffic signals turn green for you at\nthe right junctions, so you reach faster.",
  },
];
export default function OnboardingScreen() {
  const { width: windowWidth, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const width = Math.min(windowWidth, 600);
  const available = height - insets.top - insets.bottom;
  const artHeight = Math.min(width * 1.17, available * 0.58);
  const [index, setIndex] = useState(0);
  const list = useRef<FlatList<(typeof slides)[number]>>(null);
  const { dispatch, state } = useApp();
  const complete = () => dispatch({ type: "onboard" });
  function go(next: number) {
    setIndex(next);
    list.current?.scrollToOffset({
      offset: next * width,
      animated: !state.settings.reducedMotion,
    });
  }
  return (
    <SafeAreaView style={s.safe}>
      <View style={{ width, flex: 1, alignSelf: "center" }}>
        <FlatList
          key={width}
          ref={list}
          data={slides}
          horizontal
          pagingEnabled
          showsHorizontalScrollIndicator={false}
          keyExtractor={(_, i) => String(i)}
          initialScrollIndex={index}
          getItemLayout={(_, i) => ({
            length: width,
            offset: width * i,
            index: i,
          })}
          onMomentumScrollEnd={(e) =>
            setIndex(Math.round(e.nativeEvent.contentOffset.x / width))
          }
          renderItem={({ item, index: page }) => (
            <ScrollView
              style={{ width }}
              contentContainerStyle={{ minHeight: available }}
              showsVerticalScrollIndicator={false}
            >
              <View style={{ height: artHeight, width }}>
                <Image
                  source={item.image}
                  style={[
                    StyleSheet.absoluteFill,
                    { width: "100%", height: "100%" },
                  ]}
                  resizeMode="cover"
                  accessibilityLabel={
                    [
                      "Ambulance starting an emergency journey",
                      "Ambulance sharing its route to hospital",
                      "Ambulance approaching a green traffic signal",
                    ][page]
                  }
                />
                <LinearGradient
                  colors={["#FFFFFF00", "#FFFFFF"]}
                  style={s.fade}
                />
                <View style={[s.sceneCopy, { top: artHeight * 0.075 }]}>
                  <Txt
                    style={[
                      s.eyebrow,
                      {
                        fontSize: width < 370 ? 23 : 26,
                        lineHeight: width < 370 ? 28 : 31,
                      },
                    ]}
                  >
                    {item.eyebrow}
                  </Txt>
                  <View style={s.dash} />
                  <Txt style={s.sceneNote}>{item.note}</Txt>
                </View>
                {page !== 1 && (
                  <View
                    style={[
                      s.sign,
                      {
                        top: artHeight * (page === 0 ? 0.24 : 0.265),
                        right: width * (page === 0 ? 0.028 : 0.075),
                        width: width * (page === 0 ? 0.33 : 0.23),
                      },
                    ]}
                  >
                    <Txt
                      style={{
                        textAlign: "center",
                        color: "#E2EDFF",
                        fontSize: width * (page === 0 ? 0.021 : 0.0175),
                        lineHeight: width * (page === 0 ? 0.026 : 0.022),
                        fontWeight: "700",
                      }}
                    >
                      PRIORITY{"\n"}FOR{"\n"}EMERGENCY VEHICLES
                    </Txt>
                  </View>
                )}
                {page === 1 && (
                  <>
                    <View
                      style={[
                        s.sharing,
                        { top: artHeight * 0.42, left: width * 0.25 },
                      ]}
                    >
                      <Icon name="broadcast" size={27} color={c.green} />
                      <View>
                        <Txt
                          style={{
                            fontSize: 10,
                            lineHeight: 14,
                            fontWeight: "600",
                          }}
                        >
                          Live Location Sharing
                        </Txt>
                        <Txt muted style={{ fontSize: 9, lineHeight: 13 }}>
                          Tracking to control center
                        </Txt>
                      </View>
                    </View>
                    <View style={[s.eta, { top: artHeight * 0.6 }]}>
                      <Icon name="navigation" color={c.green} size={19} />
                      <Txt
                        style={{ color: c.green, fontSize: 12, lineHeight: 16 }}
                      >
                        Live{"\n"}ETA
                      </Txt>
                    </View>
                  </>
                )}
              </View>
              <View style={s.copy}>
                <Txt
                  accessibilityRole="header"
                  style={[s.title, { fontSize: width < 370 ? 27 : 30 }]}
                >
                  {item.title}
                </Txt>
                <Txt
                  style={[
                    s.title,
                    { color: c.blue, fontSize: width < 370 ? 29 : 32 },
                  ]}
                >
                  {item.accent}
                </Txt>
                <Txt muted style={s.body}>
                  {item.body}
                </Txt>
              </View>
              <View style={s.controls}>
                <Row
                  style={{ justifyContent: "center", gap: 1, marginBottom: 12 }}
                >
                  {slides.map((_, dot) => (
                    <Pressable
                      key={dot}
                      accessibilityRole="button"
                      accessibilityLabel={`Onboarding page ${dot + 1}`}
                      accessibilityState={{ selected: page === dot }}
                      onPress={() => go(dot)}
                      style={s.dotTarget}
                    >
                      <View
                        style={[
                          s.dot,
                          {
                            backgroundColor: page === dot ? c.blue : "#DCE7F9",
                          },
                        ]}
                      />
                    </Pressable>
                  ))}
                </Row>
                <Button
                  title={page === 2 ? "Get Started" : "Next"}
                  tone="red"
                  edgeIcon
                  onPress={() => (page === 2 ? complete() : go(page + 1))}
                />
                <Pressable
                  accessibilityRole="button"
                  onPress={complete}
                  style={s.skip}
                >
                  <Txt
                    style={{ fontSize: 18, fontWeight: "500", color: c.blue }}
                  >
                    Skip
                  </Txt>
                </Pressable>
              </View>
            </ScrollView>
          )}
        />
      </View>
    </SafeAreaView>
  );
}
const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "white" },
  fade: { position: "absolute", height: 32, bottom: 0, left: 0, right: 0 },
  sceneCopy: { position: "absolute", left: "7%", maxWidth: "48%" },
  eyebrow: { fontWeight: "700", color: "#758FB3", letterSpacing: -0.5 },
  dash: {
    width: 28,
    height: 4,
    borderRadius: 3,
    backgroundColor: "#FF8791",
    marginVertical: 14,
  },
  sceneNote: { color: "#7F99BA", fontSize: 13, lineHeight: 17 },
  sign: { position: "absolute", transform: [{ rotate: "-7deg" }] },
  sharing: {
    position: "absolute",
    backgroundColor: "white",
    padding: 10,
    borderRadius: 14,
    flexDirection: "row",
    gap: 7,
    alignItems: "center",
    ...shadow,
  },
  eta: {
    position: "absolute",
    right: 12,
    padding: 8,
    borderRadius: 10,
    backgroundColor: "#F8FFFC",
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    ...shadow,
  },
  copy: { alignItems: "center", paddingHorizontal: 16, marginTop: 2 },
  title: {
    fontWeight: "700",
    color: c.heading,
    textAlign: "center",
    lineHeight: 37,
    letterSpacing: -0.65,
  },
  body: { textAlign: "center", fontSize: 16, lineHeight: 23, marginTop: 13 },
  controls: {
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 12,
    marginTop: "auto",
  },
  dotTarget: {
    minWidth: 44,
    minHeight: 44,
    justifyContent: "center",
    alignItems: "center",
  },
  dot: { width: 9, height: 9, borderRadius: 5 },
  skip: {
    minHeight: 52,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 8,
  },
});
