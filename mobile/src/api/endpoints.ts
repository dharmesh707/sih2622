import type { ApiClient } from "./client";
import { malformedError } from "./errors";
import { SERVER_DECISIONS, type ActivitySummary, type EventDetail, type Project, type ReportResponse } from "../types";

const isObject = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;

export async function getProjects(api: ApiClient): Promise<Project[]> {
  const body = await api<unknown>("/projects");
  if (!Array.isArray(body) || !body.every((p) => isObject(p) && typeof p.id === "number" && typeof p.name === "string")) {
    throw malformedError();
  }
  return body as Project[];
}

export interface SubmitReportInput {
  projectId: number;
  text: string;
  clientReportId: string;
}

export async function submitReport(api: ApiClient, input: SubmitReportInput): Promise<ReportResponse> {
  const body = await api<unknown>("/reports", {
    method: "POST",
    body: { project_id: input.projectId, text: input.text, source: "mobile", client_report_id: input.clientReportId },
  });
  if (
    !isObject(body) ||
    typeof body.report_id !== "number" ||
    typeof body.event_id !== "number" ||
    !isObject(body.event) ||
    !isObject(body.match) ||
    !SERVER_DECISIONS.includes(body.match.decision as never)
  ) {
    throw malformedError();
  }
  return body as unknown as ReportResponse;
}

export async function getEvent(api: ApiClient, eventId: number): Promise<EventDetail> {
  const body = await api<unknown>(`/events/${eventId}`);
  if (!isObject(body) || typeof body.id !== "number" || !isObject(body.decision)) throw malformedError();
  return body as unknown as EventDetail;
}

export async function getActivity(api: ApiClient, activityId: number): Promise<ActivitySummary> {
  const body = await api<unknown>(`/activities/${activityId}`);
  if (!isObject(body) || typeof body.activity_code !== "string") throw malformedError();
  return {
    id: activityId,
    activity_code: body.activity_code,
    description: String(body.description ?? ""),
    location: typeof body.location === "string" ? body.location : null,
  };
}
