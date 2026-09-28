// In-process stand-in for the FastAPI backend, speaking real HTTP semantics through fetch.
// Response bodies copy what the real backend returned in the 2026-09-28 smoke test.
// The demo project deliberately has id 7 so any hard-coded project 1 in the app fails the tests.

export const TOKEN = "test-token-123";
export const PROJECT = { id: 7, name: "OIL Demo Project", created_at: "2026-09-28T11:02:58Z" };

const ACTIVITIES: Record<number, { id: number; activity_code: string; description: string; location: string }> = {
  2: { id: 2, activity_code: "PIP-L5-002", description: "Erect line XX102 spool 002", location: "R03" },
  4: { id: 4, activity_code: "ROT-L5-004", description: "Install pump CT-103 004", location: "Unit 2" },
};

function matchFor(text: string) {
  if (/XX102/i.test(text)) {
    return {
      event: { discipline: "piping", identifiers: ["XX102"], location_terms: "R03", progress: 100, inference_note: null },
      match: { decision: "AUTO_MATCHED", reason: "top score 0.965 >= 0.82 and margin 0.531 >= 0.12", top_score: 0.965, second_score: 0.434, margin: 0.531, activity_id: 2 },
    };
  }
  if (/CT103/i.test(text)) {
    return {
      event: { discipline: "rotating_equipment", identifiers: ["CT103"], location_terms: null, progress: 50, inference_note: null },
      match: { decision: "REVIEW_REQUIRED", reason: "margin 0.000 to runner-up below 0.12", top_score: 0.907, second_score: 0.907, margin: 0, activity_id: 4 },
    };
  }
  return {
    event: { discipline: null, identifiers: ["ZZ-999"], location_terms: null, progress: 20, inference_note: null },
    match: { decision: "UNMATCHED", reason: "report explicitly names an unknown work package", top_score: 0.262, second_score: 0.257, margin: 0.004, activity_id: null },
  };
}

export interface ReceivedReport {
  project_id: number;
  text: string;
  source: string;
  client_report_id: string;
}

export function createFakeServer() {
  const server = {
    offline: false,
    hang: false, // never answer (for timeouts)
    failNext: [] as number[], // statuses to return for the next POST /reports calls
    dropResponseOnce: false, // process the report but lose the reply (client sees a network error)
    received: [] as ReceivedReport[], // every POST /reports body, including replays
    reports: new Map<string, { response: Record<string, unknown>; text: string }>(),
    decisions: new Map<number, { decision: string; activity_id: number | null }>(),
    lastAuthHeader: null as string | null,
    fetch: null as unknown as typeof fetch,
    approve(eventId: number) {
      const d = server.decisions.get(eventId)!;
      server.decisions.set(eventId, { ...d, decision: "APPROVED" });
    },
  };
  let nextId = 100;

  const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

  server.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const signal = init?.signal;
    if (server.offline) throw new TypeError("Network request failed");
    if (server.hang) {
      return new Promise<Response>((_, reject) => signal?.addEventListener("abort", () => reject(new Error("aborted"))));
    }
    const url = new URL(String(input));
    const path = url.pathname.replace(/^\/api\/v1/, "");
    const auth = new Headers(init?.headers).get("Authorization");
    server.lastAuthHeader = auth;
    if (auth !== `Bearer ${TOKEN}`) return json(401, { detail: "Authentication required" });

    if (path === "/projects") return json(200, [PROJECT]);

    if (path === "/reports" && init?.method === "POST") {
      const body = JSON.parse(String(init.body)) as ReceivedReport;
      server.received.push(body);
      const status = server.failNext.shift();
      if (status) return json(status, { detail: status === 422 ? [{ loc: ["body", "text"], msg: "field required" }] : "Service unavailable" });
      if (body.project_id !== PROJECT.id) return json(404, { detail: "Project not found" });
      const prior = server.reports.get(body.client_report_id);
      if (prior) {
        if (prior.text !== body.text) return json(409, { detail: "client_report_id was already used for a different report" });
        return json(200, { ...prior.response, replayed: true });
      }
      const { event, match } = matchFor(body.text);
      const id = nextId++;
      const response = { report_id: id, event_id: id, event: { ...event, source_text: body.text }, match, latency_ms: 50 };
      server.reports.set(body.client_report_id, { response, text: body.text });
      server.decisions.set(id, { decision: match.decision, activity_id: match.activity_id });
      if (server.dropResponseOnce) {
        server.dropResponseOnce = false;
        throw new TypeError("Network request failed");
      }
      return json(200, response);
    }

    const eventMatch = /^\/events\/(\d+)$/.exec(path);
    if (eventMatch) {
      const id = Number(eventMatch[1]);
      const decision = server.decisions.get(id);
      if (!decision) return json(404, { detail: "Event not found" });
      return json(200, { id, project_id: PROJECT.id, decision });
    }

    const activityMatch = /^\/activities\/(\d+)$/.exec(path);
    if (activityMatch) {
      const activity = ACTIVITIES[Number(activityMatch[1])];
      return activity ? json(200, activity) : json(404, { detail: "Activity not found" });
    }
    return json(404, { detail: "Not Found" });
  }) as typeof fetch;

  return server;
}

export type FakeServer = ReturnType<typeof createFakeServer>;
