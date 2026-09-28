import { router } from "expo-router";
import { View } from "react-native";

import { Body, Button, Card, ConnectionBanner, Screen, Title, styles } from "../components/ui";
import { useApp } from "../state/AppContext";

export default function HomeScreen() {
  const app = useApp();
  const unsent = app.reports.filter((r) => r.sync_state !== "submitted").length;
  const failed = app.reports.filter((r) => r.sync_state === "failed").length;

  return (
    <Screen>
      <ConnectionBanner />
      <Card>
        <Body muted>Reporting to</Body>
        <Title>{app.project?.name ?? "No project selected"}</Title>
        {app.workerName ? <Body muted>Signed on this phone as {app.workerName}</Body> : null}
      </Card>

      <Button label="Record Field Update" onPress={() => router.push("/record")} disabled={!app.project} />

      <View style={styles.row}>
        <View style={{ flex: 1, minWidth: 150 }}>
          <Button variant="secondary" label={unsent ? `Pending Sync (${unsent})` : "Pending Sync"} onPress={() => router.push("/pending")} />
        </View>
        <View style={{ flex: 1, minWidth: 150 }}>
          <Button variant="secondary" label={`My Reports (${app.reports.length})`} onPress={() => router.push("/reports")} />
        </View>
      </View>
      <View style={styles.row}>
        <View style={{ flex: 1, minWidth: 150 }}>
          <Button variant="secondary" label="Change Project" onPress={() => router.push("/projects")} />
        </View>
        <View style={{ flex: 1, minWidth: 150 }}>
          <Button variant="secondary" label="Settings" onPress={() => router.push("/settings")} />
        </View>
      </View>
      {failed ? <Body>{failed} report(s) need attention in Pending Sync.</Body> : null}
    </Screen>
  );
}
