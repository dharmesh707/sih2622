// Shapes verified against backend/app.py (POST /reports, GET /events/{id}, GET /activities/{id}, GET /projects).

export type ServerDecision = "AUTO_MATCHED" | "REVIEW_REQUIRED" | "UNMATCHED" | "APPROVED" | "REJECTED";
export const SERVER_DECISIONS: readonly ServerDecision[] = ["AUTO_MATCHED", "REVIEW_REQUIRED", "UNMATCHED", "APPROVED", "REJECTED"];

export type SyncState = "queued" | "syncing" | "submitted" | "failed";

export interface Project {
  id: number;
  name: string;
  created_at?: string;
}

export interface ExtractedEvent {
  discipline: string | null;
  identifiers: string[];
  location_terms: string | null;
  progress: number | null;
  inference_note?: string | null;
  source_text: string;
}

export interface MatchResult {
  decision: ServerDecision;
  reason: string;
  top_score: number;
  second_score: number;
  margin: number;
  activity_id: number | null;
}

export interface ReportResponse {
  report_id: number;
  event_id: number;
  event: ExtractedEvent;
  match: MatchResult;
  replayed?: boolean;
}

export interface EventDetail {
  id: number;
  project_id: number;
  decision: { decision?: ServerDecision; activity_id?: number | null; comment?: string | null };
}

export interface ActivitySummary {
  id: number;
  activity_code: string;
  description: string;
  location: string | null;
}

// One field report as stored on the device. Local sync state and the server's decision are
// deliberately separate fields: "queued" is never an AUTO_MATCHED.
export interface LocalReport {
  local_id: string; // also sent as client_report_id so retries cannot create duplicates
  project_id: number;
  project_name: string;
  text: string;
  source: "mobile";
  worker_name: string | null;
  created_at: string;
  sync_state: SyncState;
  retry_count: number;
  next_attempt_at: string | null;
  last_error: string | null;
  server_report_id: number | null;
  server_event_id: number | null;
  server_response: ReportResponse | null;
  server_decision: ServerDecision | null;
  activity: ActivitySummary | null;
  server_checked_at: string | null;
}
