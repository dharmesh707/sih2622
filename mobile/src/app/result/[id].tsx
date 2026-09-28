import { router, useLocalSearchParams } from "expo-router";

import { ReportOutcome } from "../../components/ReportViews";
import { Button, Notice, Screen, Title } from "../../components/ui";
import { useApp } from "../../state/AppContext";

// Shown right after Submit: the actual server result, or the offline/failed state.
export default function ResultScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const app = useApp();
  const report = app.reports.find((r) => r.local_id === id);

  if (!report) {
    return (
      <Screen>
        <Notice tone="bad">This report was not found on the device.</Notice>
        <Button label="Home" onPress={() => router.replace("/home")} />
      </Screen>
    );
  }

  const heading =
    report.sync_state === "submitted"
      ? "Sent to ProgressSync"
      : report.sync_state === "failed"
        ? "Not sent — needs attention"
        : "Saved on this phone";

  return (
    <Screen>
      <Title>{heading}</Title>
      {report.sync_state === "queued" && report.last_error ? <Notice tone="warn">{report.last_error}</Notice> : null}
      <ReportOutcome report={report} />
      {report.sync_state === "failed" ? <Button label="Retry now" onPress={() => app.retry(report.local_id)} /> : null}
      <Button label="Record another update" onPress={() => router.replace("/record")} />
      <Button label="Home" variant="secondary" onPress={() => router.replace("/home")} />
    </Screen>
  );
}
