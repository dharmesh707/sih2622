import type { ApiClient } from "../api/client";
import { getActivity, getEvent, submitReport } from "../api/endpoints";
import { toApiError } from "../api/errors";
import type { LocalReport, Project } from "../types";
import type { Store } from "./store";

export const MAX_AUTO_RETRIES = 8;
const BASE_DELAY_MS = 5_000;
const MAX_DELAY_MS = 5 * 60_000;

// Exponential backoff with a cap: 5s, 10s, 20s ... 5 min.
export function backoffMs(retryCount: number): number {
  return Math.min(BASE_DELAY_MS * 2 ** Math.max(0, retryCount - 1), MAX_DELAY_MS);
}

export interface QueueDeps {
  store: Store;
  api: () => ApiClient | null; // null until the connection is configured
  newId: () => string;
  now?: () => Date;
}

export function createQueue({ store, api, newId, now = () => new Date() }: QueueDeps) {
  // Every operation that can send runs one at a time, so a report is never in flight twice.
  let chain: Promise<unknown> = Promise.resolve();
  const exclusive = <T>(fn: () => Promise<T>): Promise<T> => {
    const next = chain.then(fn, fn);
    chain = next.catch(() => undefined);
    return next;
  };
  let pendingSync: Promise<void> | null = null;

  async function send(report: LocalReport): Promise<LocalReport> {
    const client = api();
    if (!client) return report;
    const syncing = { ...report, sync_state: "syncing" as const };
    await store.putReport(syncing);
    try {
      // local_id doubles as client_report_id: if an earlier attempt reached the server but the reply was
      // lost, the server replays that result instead of creating a second event.
      const response = await submitReport(client, { projectId: report.project_id, text: report.text, clientReportId: report.local_id });
      const submitted: LocalReport = {
        ...syncing,
        sync_state: "submitted",
        last_error: null,
        next_attempt_at: null,
        server_report_id: response.report_id,
        server_event_id: response.event_id,
        server_response: response,
        server_decision: response.match.decision,
        server_checked_at: now().toISOString(),
      };
      await store.putReport(submitted);
      return enrichActivity(client, submitted, response.match.activity_id);
    } catch (error) {
      const e = toApiError(error);
      const retryCount = report.retry_count + 1;
      const giveUp = !e.retryable || retryCount >= MAX_AUTO_RETRIES;
      const failed: LocalReport = {
        ...syncing,
        sync_state: giveUp ? "failed" : "queued",
        retry_count: retryCount,
        last_error: giveUp && e.retryable ? `${e.message} Automatic retries stopped after ${retryCount} attempts.` : e.message,
        next_attempt_at: giveUp ? null : new Date(now().getTime() + backoffMs(retryCount)).toISOString(),
      };
      await store.putReport(failed);
      return failed;
    }
  }

  async function enrichActivity(client: ApiClient, report: LocalReport, activityId: number | null | undefined): Promise<LocalReport> {
    if (!activityId || report.activity?.id === activityId) return report;
    try {
      const withActivity = { ...report, activity: await getActivity(client, activityId) };
      await store.putReport(withActivity);
      return withActivity;
    } catch {
      return report; // the decision is already stored; the activity label is only a convenience
    }
  }

  // Sends every queued report whose retry time has come. One run at a time, oldest first.
  function syncDue(force = false): Promise<void> {
    if (pendingSync) return pendingSync;
    pendingSync = exclusive(async () => {
      try {
        const due = (await store.listReports())
          .filter((r) => r.sync_state === "queued" && (force || !r.next_attempt_at || r.next_attempt_at <= now().toISOString()))
          .reverse();
        for (const report of due) {
          const result = await send(report);
          if (result.sync_state === "queued" && !force) break; // server unreachable: stop this round
        }
      } finally {
        pendingSync = null;
      }
    });
    return pendingSync;
  }

  return {
    // Persist first, then try to send: a report is never only in memory.
    submit(text: string, project: Project, workerName: string | null): Promise<LocalReport> {
      const report: LocalReport = {
        local_id: newId(),
        project_id: project.id,
        project_name: project.name,
        text,
        source: "mobile",
        worker_name: workerName,
        created_at: now().toISOString(),
        sync_state: "queued",
        retry_count: 0,
        next_attempt_at: null,
        last_error: null,
        server_report_id: null,
        server_event_id: null,
        server_response: null,
        server_decision: null,
        activity: null,
        server_checked_at: null,
      };
      return exclusive(async () => {
        await store.putReport(report);
        return send(report);
      });
    },

    syncDue,

    // Manual retry: resets the automatic retry budget.
    retry(localId: string): Promise<LocalReport | null> {
      return exclusive(async () => {
        const report = await store.getReport(localId);
        if (!report || report.sync_state === "submitted") return report;
        return send({ ...report, sync_state: "queued", retry_count: 0, next_attempt_at: null });
      });
    },

    // Only explicit, user-confirmed discard deletes an unsent report.
    discard(localId: string): Promise<void> {
      return exclusive(async () => {
        const report = await store.getReport(localId);
        if (report && report.sync_state !== "submitted") await store.deleteReport(localId);
      });
    },

    // A report left "syncing" by an app kill is safe to resend thanks to client_report_id.
    recoverInterrupted(): Promise<void> {
      return exclusive(async () => {
        for (const r of await store.listReports()) {
          if (r.sync_state === "syncing") await store.putReport({ ...r, sync_state: "queued" });
        }
      });
    },

    // Pulls the latest planner decision for a submitted report (e.g. APPROVED after confirmation).
    async refresh(localId: string): Promise<LocalReport | null> {
      const report = await store.getReport(localId);
      const client = api();
      if (!report || !client || report.server_event_id === null) return report;
      const event = await getEvent(client, report.server_event_id);
      const decision = event.decision.decision ?? report.server_decision;
      const updated = { ...report, server_decision: decision, server_checked_at: now().toISOString() };
      await store.putReport(updated);
      return enrichActivity(client, updated, event.decision.activity_id ?? report.activity?.id ?? null);
    },
  };
}

export type Queue = ReturnType<typeof createQueue>;
