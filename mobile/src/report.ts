import type { LocalReport } from "./types";

export const MAX_REPORT_LENGTH = 20000; // backend ReportIn.text max_length

export function validateReportText(text: string): string | null {
  const trimmed = text.trim();
  if (trimmed.length < 3) return "Describe what happened on site.";
  if (trimmed.length > MAX_REPORT_LENGTH) return "This report is too long. Keep it under 20,000 characters.";
  return null;
}

export function parseProgress(input: string): { value: number } | { error: string } {
  const trimmed = input.trim().replace(/%$/, "");
  if (!/^\d{1,3}(\.\d+)?$/.test(trimmed)) return { error: "Enter a number from 0 to 100." };
  const value = Number(trimmed);
  if (value < 0 || value > 100) return { error: "Progress must be between 0 and 100." };
  return { value };
}

export type ProgressShortcut = "started" | "completed" | number | null;

export interface Shortcuts {
  discipline: string | null;
  identifier: string;
  location: string;
  progress: ProgressShortcut;
}

export const EMPTY_SHORTCUTS: Shortcuts = { discipline: null, identifier: "", location: "", progress: null };

const has = (text: string, part: string) => text.toLowerCase().includes(part.toLowerCase());

// Shortcuts only add plain words to the worker's own sentence; the backend still does all extraction.
// The composed text is shown to the worker before sending, and exactly that text is sent.
export function composeReport(freeText: string, s: Shortcuts): string {
  let text = freeText.trim().replace(/[.\s]+$/, "");
  const parts: string[] = [];
  if (s.identifier.trim() && !has(text, s.identifier.trim())) parts.push(s.identifier.trim());
  if (s.location.trim() && !has(text, s.location.trim())) parts.push(`at ${s.location.trim()}`);
  if (s.progress === "started") parts.push("started");
  else if (s.progress === "completed") parts.push("completed, 100%");
  else if (typeof s.progress === "number") parts.push(`${s.progress}%`);
  if (parts.length) text = text ? `${text}, ${parts.join(", ")}` : parts.join(", ");
  if (s.discipline && !has(text, s.discipline)) text = `${s.discipline}: ${text}`;
  return text ? `${text}.` : "";
}

export type StatusTone = "neutral" | "info" | "warn" | "good" | "bad";

// The one place that turns local sync state + server decision into worker wording.
// "Schedule updated" appears only when the backend has recorded an APPROVED decision.
export function reportStatus(r: LocalReport): { label: string; next: string; tone: StatusTone } {
  if (r.sync_state === "queued") {
    return r.last_error
      ? { label: "Saved offline — waiting for connection", next: "It will be sent automatically when the server is reachable.", tone: "warn" }
      : { label: "Pending sync", next: "Waiting to be sent.", tone: "warn" };
  }
  if (r.sync_state === "syncing") return { label: "Sending…", next: "Sending to ProgressSync.", tone: "info" };
  if (r.sync_state === "failed") return { label: "Failed — needs attention", next: r.last_error ?? "Tap Retry to send again.", tone: "bad" };
  switch (r.server_decision) {
    case "AUTO_MATCHED":
      return { label: "Matched — awaiting planner confirmation", next: "Planner confirmation required. The schedule has not changed yet.", tone: "info" };
    case "REVIEW_REQUIRED":
      return { label: "Review required", next: "A planner will choose the right activity. The schedule has not changed yet.", tone: "warn" };
    case "UNMATCHED":
      return { label: "Unmatched — observation saved", next: "No schedule activity was linked. A planner will review it; the schedule has not changed.", tone: "warn" };
    case "APPROVED":
      return { label: "Schedule updated", next: "A planner confirmed this report and the schedule was updated.", tone: "good" };
    case "REJECTED":
      return { label: "Rejected by planner", next: "A planner rejected this report. Nothing was written to the schedule.", tone: "bad" };
    default:
      return { label: "Submitted", next: "Received by ProgressSync.", tone: "info" };
  }
}

export type ReportFilter = "all" | "pending" | "submitted" | "review" | "unmatched" | "failed";

export function matchesFilter(r: LocalReport, filter: ReportFilter): boolean {
  switch (filter) {
    case "all":
      return true;
    case "pending":
      return r.sync_state === "queued" || r.sync_state === "syncing";
    case "failed":
      return r.sync_state === "failed";
    case "submitted":
      return r.sync_state === "submitted";
    case "review":
      return r.sync_state === "submitted" && (r.server_decision === "REVIEW_REQUIRED" || r.server_decision === "AUTO_MATCHED");
    case "unmatched":
      return r.sync_state === "submitted" && r.server_decision === "UNMATCHED";
  }
}
