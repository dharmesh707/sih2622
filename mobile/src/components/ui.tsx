import type { ReactNode } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View, type TextInputProps } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import type { StatusTone } from "../report";
import { useApp, type Connection } from "../state/AppContext";

export const colors = {
  ink: "#0F172A",
  muted: "#475569",
  line: "#CBD5E1",
  bg: "#F8FAFC",
  card: "#FFFFFF",
  primary: "#0B4FD8",
  primaryInk: "#FFFFFF",
  good: "#0F7B3F",
  warn: "#A15C00",
  bad: "#B42318",
  info: "#0B4FD8",
  neutral: "#475569",
};

const toneColor: Record<StatusTone, string> = { good: colors.good, warn: colors.warn, bad: colors.bad, info: colors.info, neutral: colors.neutral };

export function Screen({ children, scroll = true }: { children: ReactNode; scroll?: boolean }) {
  const body = scroll ? (
    <ScrollView contentContainerStyle={styles.screenBody} keyboardShouldPersistTaps="handled">
      {children}
    </ScrollView>
  ) : (
    <View style={[styles.screenBody, styles.fill]}>{children}</View>
  );
  return (
    <SafeAreaView style={styles.screen} edges={["bottom", "left", "right"]}>
      <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        {body}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

export function Button({
  label,
  onPress,
  variant = "primary",
  disabled,
  busy,
  hint,
}: {
  label: string;
  onPress: () => void;
  variant?: "primary" | "secondary" | "danger";
  disabled?: boolean;
  busy?: boolean;
  hint?: string;
}) {
  const inactive = disabled || busy;
  return (
    <Pressable
      role="button"
      aria-label={label}
      aria-disabled={inactive}
      aria-busy={busy}
      accessibilityHint={hint}
      disabled={inactive}
      onPress={onPress}
      style={({ pressed }) => [styles.button, styles[variant], inactive && styles.disabled, pressed && styles.pressed]}
    >
      {busy ? <ActivityIndicator color={variant === "primary" ? colors.primaryInk : colors.primary} /> : null}
      <Text style={[styles.buttonText, variant === "primary" ? styles.primaryText : variant === "danger" ? styles.dangerText : styles.secondaryText]}>{label}</Text>
    </Pressable>
  );
}

export function Chip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable role="button" aria-label={label} aria-selected={selected} onPress={onPress} style={[styles.chip, selected && styles.chipSelected]}>
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Text>
    </Pressable>
  );
}

export function Field({ label, error, ...input }: TextInputProps & { label: string; error?: string | null }) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput aria-label={label} placeholderTextColor="#64748B" style={[styles.input, input.multiline && styles.multiline, error ? styles.inputError : null]} {...input} />
      {error ? (
        <Text role="alert" style={styles.errorText}>
          {error}
        </Text>
      ) : null}
    </View>
  );
}

export function Card({ children }: { children: ReactNode }) {
  return <View style={styles.card}>{children}</View>;
}

export function Title({ children }: { children: ReactNode }) {
  return (
    <Text role="heading" style={styles.title}>
      {children}
    </Text>
  );
}

export function Body({ children, muted }: { children: ReactNode; muted?: boolean }) {
  return <Text style={[styles.body, muted && styles.muted]}>{children}</Text>;
}

export function Badge({ label, tone }: { label: string; tone: StatusTone }) {
  return (
    <View style={[styles.badge, { borderColor: toneColor[tone] }]}>
      <Text style={[styles.badgeText, { color: toneColor[tone] }]}>{label}</Text>
    </View>
  );
}

export function Notice({ tone, children }: { tone: StatusTone; children: ReactNode }) {
  return (
    <View role="alert" style={[styles.notice, { borderLeftColor: toneColor[tone] }]}>
      <Text style={styles.body}>{children}</Text>
    </View>
  );
}

const connectionLabel: Record<Connection, { label: string; tone: StatusTone }> = {
  online: { label: "Online", tone: "good" },
  offline: { label: "Offline", tone: "warn" },
  connecting: { label: "Connecting…", tone: "info" },
  server_unavailable: { label: "Server unavailable", tone: "bad" },
  unauthorized: { label: "Token rejected — open Settings", tone: "bad" },
  not_configured: { label: "Not connected", tone: "neutral" },
};

export function ConnectionBanner() {
  const { connection, reports } = useApp();
  const pending = reports.filter((r) => r.sync_state !== "submitted").length;
  const { label, tone } = connectionLabel[connection];
  return (
    <View style={styles.banner} aria-label={`Connection: ${label}`}>
      <View style={[styles.dot, { backgroundColor: toneColor[tone] }]} />
      <Text style={styles.bannerText}>{label}</Text>
      {pending ? <Text style={styles.bannerPending}>{pending} waiting to sync</Text> : null}
    </View>
  );
}

export const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  fill: { flex: 1 },
  screenBody: { padding: 16, gap: 14, paddingBottom: 40 },
  button: { minHeight: 56, borderRadius: 12, paddingHorizontal: 18, alignItems: "center", justifyContent: "center", flexDirection: "row", gap: 10 },
  primary: { backgroundColor: colors.primary },
  secondary: { backgroundColor: colors.card, borderWidth: 2, borderColor: colors.primary },
  danger: { backgroundColor: colors.card, borderWidth: 2, borderColor: colors.bad },
  disabled: { opacity: 0.45 },
  pressed: { opacity: 0.8 },
  buttonText: { fontSize: 18, fontWeight: "700" },
  primaryText: { color: colors.primaryInk },
  secondaryText: { color: colors.primary },
  dangerText: { color: colors.bad },
  chip: { minHeight: 48, paddingHorizontal: 16, borderRadius: 24, borderWidth: 2, borderColor: colors.line, backgroundColor: colors.card, justifyContent: "center" },
  chipSelected: { borderColor: colors.primary, backgroundColor: "#E0EAFF" },
  chipText: { fontSize: 16, color: colors.ink, fontWeight: "600" },
  chipTextSelected: { color: colors.primary },
  field: { gap: 6 },
  label: { fontSize: 16, fontWeight: "700", color: colors.ink },
  input: { minHeight: 52, borderWidth: 2, borderColor: colors.line, borderRadius: 10, paddingHorizontal: 14, fontSize: 18, color: colors.ink, backgroundColor: colors.card },
  multiline: { minHeight: 140, paddingTop: 12, textAlignVertical: "top" },
  inputError: { borderColor: colors.bad },
  errorText: { color: colors.bad, fontSize: 15, fontWeight: "600" },
  card: { backgroundColor: colors.card, borderRadius: 14, padding: 16, gap: 8, borderWidth: 1, borderColor: colors.line },
  title: { fontSize: 24, fontWeight: "800", color: colors.ink },
  body: { fontSize: 17, color: colors.ink, lineHeight: 24 },
  muted: { color: colors.muted },
  badge: { alignSelf: "flex-start", borderWidth: 2, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4 },
  badgeText: { fontSize: 15, fontWeight: "800" },
  notice: { backgroundColor: colors.card, borderLeftWidth: 6, borderRadius: 8, padding: 14 },
  banner: { flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" },
  dot: { width: 12, height: 12, borderRadius: 6 },
  bannerText: { fontSize: 16, fontWeight: "700", color: colors.ink },
  bannerPending: { fontSize: 15, color: colors.warn, fontWeight: "700" },
  row: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
});
