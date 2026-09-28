import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";

import { AppProvider, type AppDeps } from "../state/AppContext";
import { colors } from "./ui";

const titles: Record<string, string> = {
  index: "ProgressSync Field",
  setup: "Connection",
  projects: "Choose project",
  home: "ProgressSync Field",
  record: "Record field update",
  "result/[id]": "Report sent",
  reports: "My reports",
  "report/[id]": "Report detail",
  pending: "Pending sync",
  settings: "Settings",
};

export function AppShell({ deps }: { deps: AppDeps }) {
  return (
    <AppProvider deps={deps}>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerStyle: { backgroundColor: colors.card }, headerTitleStyle: { fontWeight: "800" }, contentStyle: { backgroundColor: colors.bg } }}>
        {Object.entries(titles).map(([name, title]) => (
          <Stack.Screen key={name} name={name} options={{ title, headerShown: name !== "index" }} />
        ))}
      </Stack>
    </AppProvider>
  );
}
