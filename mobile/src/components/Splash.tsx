import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { colors } from "./ui";

export function Splash({ message }: { message: string }) {
  return (
    <View style={s.root}>
      <Text style={s.brand}>ProgressSync</Text>
      <Text style={s.sub}>Field updates</Text>
      <ActivityIndicator size="large" color={colors.primaryInk} style={{ marginTop: 24 }} />
      <Text style={s.message}>{message}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center", padding: 24 },
  brand: { color: colors.primaryInk, fontSize: 36, fontWeight: "900" },
  sub: { color: colors.primaryInk, fontSize: 18, marginTop: 4 },
  message: { color: colors.primaryInk, fontSize: 16, marginTop: 16, textAlign: "center" },
});
