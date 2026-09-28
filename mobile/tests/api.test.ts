import { createApiClient, validateBaseUrl } from "../src/api/client";
import { getProjects, submitReport } from "../src/api/endpoints";
import { ApiError, httpError } from "../src/api/errors";
import { createFakeServer, PROJECT, TOKEN } from "./fakeServer";

const client = (server: ReturnType<typeof createFakeServer>, token = TOKEN, timeoutMs = 2000) =>
  createApiClient({ baseUrl: "https://api.example.com/", getToken: async () => token, fetchImpl: server.fetch, timeoutMs });

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    return error as ApiError;
  }
  throw new Error("expected a failure");
}

describe("API client", () => {
  it("sends the bearer token and the selected project with source=mobile", async () => {
    const server = createFakeServer();
    const api = client(server);
    const projects = await getProjects(api);
    expect(projects).toEqual([PROJECT]);
    const result = await submitReport(api, { projectId: projects[0].id, text: "Piping crew completed spool XX102 at rack 3, 100%.", clientReportId: "local-0001" });
    expect(server.lastAuthHeader).toBe(`Bearer ${TOKEN}`);
    expect(server.received[0]).toEqual({ project_id: 7, text: "Piping crew completed spool XX102 at rack 3, 100%.", source: "mobile", client_report_id: "local-0001" });
    expect(result.match.decision).toBe("AUTO_MATCHED");
  });

  it.each([
    ["Pump CT103 installed at Unit 2, 50%.", "REVIEW_REQUIRED"],
    ["ZZ-999 unknown activity at offshore platform, 20%.", "UNMATCHED"],
  ])("maps %s to %s", async (text, decision) => {
    const result = await submitReport(client(createFakeServer()), { projectId: 7, text, clientReportId: "local-0002" });
    expect(result.match.decision).toBe(decision);
  });

  it("maps 401 to a Settings hint and never puts the token in the message", async () => {
    const e = await failure(getProjects(client(createFakeServer(), "wrong-secret-token")));
    expect(e).toMatchObject({ kind: "http", status: 401, retryable: false });
    expect(e.message).toMatch(/Settings/);
    expect(e.message).not.toMatch(/wrong-secret-token/);
  });

  it("maps 422, 409 and 503 from POST /reports", async () => {
    const server = createFakeServer();
    server.failNext = [422, 503];
    const e422 = await failure(submitReport(client(server), { projectId: 7, text: "x", clientReportId: "local-0003" }));
    expect(e422).toMatchObject({ status: 422, retryable: false });
    expect(e422.message).not.toMatch(/loc|body/); // validation dumps are not shown
    const e503 = await failure(submitReport(client(server), { projectId: 7, text: "x", clientReportId: "local-0003" }));
    expect(e503).toMatchObject({ status: 503, retryable: true });
    expect(e503.message).toBe("ProgressSync is temporarily unavailable. Your report has not been written to the schedule.");

    await submitReport(client(server), { projectId: 7, text: "Spool XX102 done", clientReportId: "local-0004" });
    const e409 = await failure(submitReport(client(server), { projectId: 7, text: "different text", clientReportId: "local-0004" }));
    expect(e409).toMatchObject({ status: 409, retryable: false });
  });

  it("reports offline and timeout distinctly, both retryable", async () => {
    const server = createFakeServer();
    server.offline = true;
    expect(await failure(getProjects(client(server)))).toMatchObject({ kind: "offline", retryable: true });
    server.offline = false;
    server.hang = true;
    expect(await failure(getProjects(client(server, TOKEN, 50)))).toMatchObject({ kind: "timeout", retryable: true });
  });

  it("rejects malformed responses", async () => {
    const bad = (body: string) => createApiClient({ baseUrl: "https://x.test", getToken: async () => TOKEN, fetchImpl: (async () => new Response(body, { status: 200 })) as typeof fetch });
    expect(await failure(getProjects(bad("<html>oops</html>")))).toMatchObject({ kind: "malformed" });
    expect(await failure(getProjects(bad('{"not":"a list"}')))).toMatchObject({ kind: "malformed" });
    expect(await failure(submitReport(bad('{"report_id":1}'), { projectId: 7, text: "x", clientReportId: "local-0005" }))).toMatchObject({ kind: "malformed" });
  });
});

describe("error mapping", () => {
  it.each([
    [400, false],
    [401, false],
    [403, false],
    [404, false],
    [409, false],
    [413, false],
    [415, false],
    [422, false],
    [429, true],
    [500, true],
    [502, true],
    [503, true],
    [504, true],
  ])("status %i → retryable %s, with a plain message", (status, retryable) => {
    const e = httpError(status, "Traceback (most recent call last): ...".repeat(10));
    expect(e.retryable).toBe(retryable);
    expect(e.message).not.toMatch(/Traceback/);
    expect(e.message.length).toBeGreaterThan(10);
  });
});

describe("validateBaseUrl", () => {
  it("requires HTTPS except for local development servers", () => {
    expect(validateBaseUrl("https://progresssync.example.com/")).toEqual({ url: "https://progresssync.example.com" });
    expect(validateBaseUrl("http://192.168.1.20:8000")).toEqual({ url: "http://192.168.1.20:8000" });
    expect(validateBaseUrl("http://localhost:8000")).toEqual({ url: "http://localhost:8000" });
    expect(validateBaseUrl("http://progresssync.example.com")).toHaveProperty("error");
    expect(validateBaseUrl("progresssync.example.com")).toHaveProperty("error");
  });
});
