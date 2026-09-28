import { Pressable, Text, View } from "react-native";

import { reportStatus } from "../report";
import type { LocalReport } from "../types";
import { Badge, Body, Card, colors, styles } from "./ui";

const when = (iso: string) => new Date(iso).toLocaleString();

export function ReportCard({ report, onPress }: { report: LocalReport; onPress: () => void }) {
  const status = reportStatus(report);
  return (
    <Pressable role="button" aria-label={`Report: ${report.text}. ${status.label}`} onPress={onPress}>
      <Card>
        <Badge label={status.label} tone={status.tone} />
        <Text numberOfLines={2} style={styles.body}>
          {report.text}
        </Text>
        <Body muted>
          {when(report.created_at)} · {report.project_name}
          {report.activity ? ` · ${report.activity.activity_code}` : ""}
        </Body>
      </Card>
    </Pressable>
  );
}

function Row({ label, value }: { label: string; value: string | null | undefined }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <View style={{ gap: 2 }}>
      <Text style={[styles.label, { color: colors.muted, fontSize: 14 }]}>{label}</Text>
      <Text style={styles.body}>{value}</Text>
    </View>
  );
}

// Worker-level summary of what the server actually returned. Nothing here is inferred on the device.
export function ReportOutcome({ report, detailed = false }: { report: LocalReport; detailed?: boolean }) {
  const status = reportStatus(report);
  const response = report.server_response;
  const event = response?.event;
  const match = response?.match;
  return (
    <>
      <Card>
        <Badge label={status.label} tone={status.tone} />
        <Text style={[styles.label, { marginTop: 4 }]}>Next step</Text>
        <Body>{status.next}</Body>
      </Card>

      {report.activity ? (
        <Card>
          <Text style={styles.label}>{report.server_decision === "APPROVED" ? "Updated activity" : "Matched to"}</Text>
          <Text style={[styles.title, { fontSize: 22 }]}>{report.activity.activity_code}</Text>
          <Body>{report.activity.description}</Body>
          {report.activity.location ? <Body muted>{report.activity.location}</Body> : null}
        </Card>
      ) : null}

      <Card>
        <Row label="Your report" value={report.text} />
        <Row label="Project" value={report.project_name} />
        <Row label="Recorded by (this device)" value={report.worker_name} />
        <Row label="Saved on device" value={when(report.created_at)} />
        {report.server_report_id !== null ? <Row label="Server reference" value={`Report #${report.server_report_id} · Event #${report.server_event_id}`} /> : <Row label="Server" value="Not sent yet — stored only on this device" />}
      </Card>

      {event ? (
        <Card>
          <Text style={styles.label}>What ProgressSync understood</Text>
          <Row label="Discipline" value={event.discipline} />
          <Row label="Tags / equipment" value={event.identifiers?.join(", ")} />
          <Row label="Location" value={event.location_terms} />
          <Row label="Progress" value={event.progress === null || event.progress === undefined ? "Not stated" : `${event.progress}%`} />
          <Row label="Note" value={event.inference_note} />
        </Card>
      ) : null}

      {detailed && match ? (
        <Card>
          <Text style={styles.label}>Matching evidence</Text>
          <Row label="First decision" value={match.decision} />
          <Row label="Reason" value={match.reason} />
          <Row label="Confidence" value={`${match.top_score.toFixed(2)} (next best ${match.second_score.toFixed(2)}, gap ${match.margin.toFixed(2)})`} />
          {report.server_checked_at ? <Body muted>Checked with server {when(report.server_checked_at)}</Body> : null}
        </Card>
      ) : null}
    </>
  );
}
