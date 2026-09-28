import { router } from "expo-router";
import { useState } from "react";
import { Text, View } from "react-native";

import { confirm } from "../components/confirm";
import { ReportCard } from "../components/ReportViews";
import { Body, Button, Card, ConnectionBanner, Screen, styles } from "../components/ui";
import { useApp } from "../state/AppContext";
import type { SyncState } from "../types";

const LABELS: Record<SyncState, string> = { queued: "Waiting", syncing: "Syncing", failed: "Failed", submitted: "Submitted" };

export default function PendingScreen() {
  const app = useApp();
  const [syncing, setSyncing] = useState(false);
  const count = (s: SyncState) => app.reports.filter((r) => r.sync_state === s).length;
  const unsent = app.reports.filter((r) => r.sync_state !== "submitted");

  async function syncNow() {
    setSyncing(true);
    await app.syncNow(true);
    setSyncing(false);
  }

  return (
    <Screen>
      <ConnectionBanner />
      <View style={styles.row}>
        {(Object.keys(LABELS) as SyncState[]).map((s) => (
          <Card key={s}>
            <Text style={[styles.title, { fontSize: 22 }]}>{count(s)}</Text>
            <Body muted>{LABELS[s]}</Body>
          </Card>
        ))}
      </View>
      <Button label="Sync now" onPress={syncNow} busy={syncing} disabled={!unsent.length} />
      {unsent.length ? null : <Body muted>Everything on this phone has been sent.</Body>}
      {unsent.map((r) => (
        <View key={r.local_id} style={{ gap: 8 }}>
          <ReportCard report={r} onPress={() => router.push({ pathname: "/report/[id]", params: { id: r.local_id } })} />
          <View style={styles.row}>
            <View style={{ flex: 1 }}>
              <Button label="Retry" variant="secondary" disabled={r.sync_state === "syncing"} onPress={() => app.retry(r.local_id)} />
            </View>
            <View style={{ flex: 1 }}>
              <Button
                label="Discard"
                variant="danger"
                disabled={r.sync_state === "syncing"}
                onPress={async () => {
                  if (await confirm("Discard this unsent report?", "It has not reached ProgressSync. Discarding deletes it from this phone for good.", "Discard")) await app.discard(r.local_id);
                }}
              />
            </View>
          </View>
        </View>
      ))}
    </Screen>
  );
}
