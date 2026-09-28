import { composeReport, EMPTY_SHORTCUTS, matchesFilter, parseProgress, reportStatus, validateReportText } from "../src/report";
import type { LocalReport, ServerDecision, SyncState } from "../src/types";

const base: LocalReport = {
  local_id: "a",
  project_id: 7,
  project_name: "P",
  text: "t",
  source: "mobile",
  worker_name: null,
  created_at: "2026-09-28T10:00:00.000Z",
  sync_state: "submitted",
  retry_count: 0,
  next_attempt_at: null,
  last_error: null,
  server_report_id: 1,
  server_event_id: 1,
  server_response: null,
  server_decision: null,
  activity: null,
  server_checked_at: null,
};
const with_ = (sync_state: SyncState, server_decision: ServerDecision | null, last_error: string | null = null): LocalReport => ({ ...base, sync_state, server_decision, last_error });

describe("report validation", () => {
  it("rejects empty and too-long text", () => {
    expect(validateReportText("  ")).not.toBeNull();
    expect(validateReportText("x".repeat(20001))).not.toBeNull();
    expect(validateReportText("Spool XX102 done")).toBeNull();
  });

  it("accepts progress only within 0..100", () => {
    expect(parseProgress("0")).toEqual({ value: 0 });
    expect(parseProgress("100")).toEqual({ value: 100 });
    expect(parseProgress("42.5%")).toEqual({ value: 42.5 });
    for (const bad of ["-1", "101", "abc", "", "1e2", "50 percent"]) expect(parseProgress(bad)).toHaveProperty("error");
  });
});

describe("composeReport", () => {
  it("returns the worker's own sentence untouched apart from final punctuation", () => {
    expect(composeReport("Piping crew completed spool XX102 at rack 3, 100%", EMPTY_SHORTCUTS)).toBe("Piping crew completed spool XX102 at rack 3, 100%.");
  });

  it("adds shortcuts as plain words and skips ones already written", () => {
    expect(composeReport("Spool erected", { discipline: "Piping", identifier: "XX102", location: "rack 3", progress: "completed" })).toBe(
      "Piping: Spool erected, XX102, at rack 3, completed, 100%.",
    );
    expect(composeReport("Piping spool XX102 at rack 3", { discipline: "Piping", identifier: "XX102", location: "rack 3", progress: 50 })).toBe("Piping spool XX102 at rack 3, 50%.");
    expect(composeReport("", { ...EMPTY_SHORTCUTS, identifier: "P-301", progress: "started" })).toBe("P-301, started.");
  });
});

describe("reportStatus", () => {
  it("says 'Schedule updated' only for an APPROVED server decision", () => {
    const cases: [LocalReport, string][] = [
      [with_("queued", null), "Pending sync"],
      [with_("queued", null, "No connection"), "Saved offline — waiting for connection"],
      [with_("syncing", null), "Sending…"],
      [with_("failed", null, "401"), "Failed — needs attention"],
      [with_("submitted", null), "Submitted"],
      [with_("submitted", "AUTO_MATCHED"), "Matched — awaiting planner confirmation"],
      [with_("submitted", "REVIEW_REQUIRED"), "Review required"],
      [with_("submitted", "UNMATCHED"), "Unmatched — observation saved"],
      [with_("submitted", "REJECTED"), "Rejected by planner"],
      [with_("submitted", "APPROVED"), "Schedule updated"],
    ];
    for (const [report, label] of cases) expect(reportStatus(report).label).toBe(label);
    const updated = cases.filter(([r]) => reportStatus(r).label === "Schedule updated");
    expect(updated.map(([r]) => r.server_decision)).toEqual(["APPROVED"]);
  });

  it("keeps a queued report distinct from a matched one", () => {
    expect(reportStatus(with_("queued", null)).label).not.toMatch(/match/i);
  });
});

describe("matchesFilter", () => {
  it("sorts reports into the history filters", () => {
    expect(matchesFilter(with_("queued", null), "pending")).toBe(true);
    expect(matchesFilter(with_("failed", null), "failed")).toBe(true);
    expect(matchesFilter(with_("submitted", "REVIEW_REQUIRED"), "review")).toBe(true);
    expect(matchesFilter(with_("submitted", "UNMATCHED"), "unmatched")).toBe(true);
    expect(matchesFilter(with_("submitted", "UNMATCHED"), "review")).toBe(false);
    expect(matchesFilter(with_("queued", null), "submitted")).toBe(false);
  });
});
