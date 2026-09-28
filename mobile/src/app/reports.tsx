import { router } from "expo-router";
import { useState } from "react";
import { View } from "react-native";

import { ReportCard } from "../components/ReportViews";
import { Body, Button, Chip, Screen, styles } from "../components/ui";
import { matchesFilter, type ReportFilter } from "../report";
import { useApp } from "../state/AppContext";

const FILTERS: { label: string; value: ReportFilter }[] = [
  { label: "All", value: "all" },
  { label: "Pending", value: "pending" },
  { label: "Submitted", value: "submitted" },
  { label: "Review", value: "review" },
  { label: "Unmatched", value: "unmatched" },
  { label: "Failed", value: "failed" },
];

const OPEN = new Set(["AUTO_MATCHED", "REVIEW_REQUIRED", "UNMATCHED"]);

export default function ReportsScreen() {
  const app = useApp();
  const [filter, setFilter] = useState<ReportFilter>("all");
  const [checking, setChecking] = useState(false);
  const shown = app.reports.filter((r) => matchesFilter(r, filter));

  // Ask the server for planner decisions on reports that are still open.
  async function checkUpdates() {
    setChecking(true);
    for (const r of app.reports) {
      if (r.sync_state === "submitted" && r.server_decision && OPEN.has(r.server_decision)) await app.refreshReport(r.local_id);
    }
    setChecking(false);
  }

  return (
    <Screen>
      <View style={styles.row}>
        {FILTERS.map((f) => (
          <Chip key={f.value} label={f.label} selected={filter === f.value} onPress={() => setFilter(f.value)} />
        ))}
      </View>
      <Button label="Check for planner updates" variant="secondary" onPress={checkUpdates} busy={checking} disabled={app.connection !== "online"} />
      {shown.length ? null : <Body muted>No reports here yet.</Body>}
      {shown.map((r) => (
        <ReportCard key={r.local_id} report={r} onPress={() => router.push({ pathname: "/report/[id]", params: { id: r.local_id } })} />
      ))}
    </Screen>
  );
}
