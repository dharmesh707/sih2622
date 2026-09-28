import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";

import { confirm } from "../../components/confirm";
import { ReportOutcome } from "../../components/ReportViews";
import { Button, Notice, Screen } from "../../components/ui";
import { useApp } from "../../state/AppContext";

export default function ReportDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const app = useApp();
  const report = app.reports.find((r) => r.local_id === id);
  const [busy, setBusy] = useState(false);

  // Pick up any planner decision made since the report was sent.
  useEffect(() => {
    if (report?.sync_state === "submitted" && app.connection === "online") void app.refreshReport(report.local_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per open
  }, [id]);

  if (!report) {
    return (
      <Screen>
        <Notice tone="bad">This report is no longer on the device.</Notice>
      </Screen>
    );
  }

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    await fn();
    setBusy(false);
  }

  async function discard() {
    const ok = await confirm("Discard this unsent report?", "It has not reached ProgressSync. Discarding deletes it from this phone for good.", "Discard");
    if (!ok) return;
    await app.discard(report!.local_id);
    router.back();
  }

  const unsent = report.sync_state !== "submitted";
  return (
    <Screen>
      <ReportOutcome report={report} detailed />
      {report.sync_state === "submitted" ? (
        <Button label="Check server status" variant="secondary" busy={busy} onPress={() => run(() => app.refreshReport(report.local_id))} />
      ) : null}
      {unsent ? <Button label="Retry now" busy={busy} disabled={report.sync_state === "syncing"} onPress={() => run(() => app.retry(report.local_id))} /> : null}
      {unsent ? <Button label="Discard report" variant="danger" onPress={discard} disabled={report.sync_state === "syncing"} /> : null}
    </Screen>
  );
}
