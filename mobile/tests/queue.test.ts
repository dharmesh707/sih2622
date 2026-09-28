import { createApiClient } from "../src/api/client";
import { backoffMs, createQueue, MAX_AUTO_RETRIES } from "../src/offline/queue";
import { createMemoryStore, type Store } from "../src/offline/store";
import { createFakeServer, PROJECT, TOKEN, type FakeServer } from "./fakeServer";

const CONFIDENT = "Piping crew completed spool XX102 at rack 3, 100%.";

function setup(server: FakeServer = createFakeServer(), store: Store = createMemoryStore(), clock = { t: Date.parse("2026-09-28T10:00:00Z") }) {
  const api = createApiClient({ baseUrl: "https://api.test", getToken: async () => TOKEN, fetchImpl: server.fetch, timeoutMs: 200 });
  let n = 0;
  const queue = createQueue({ store, api: () => api, newId: () => `local-${String(++n).padStart(4, "0")}-${clock.t}`, now: () => new Date(clock.t) });
  return { server, store, clock, queue };
}

describe("offline queue", () => {
  it("online submit → submitted, with the server result and activity stored", async () => {
    const { queue, server, store } = setup();
    const report = await queue.submit(CONFIDENT, PROJECT, "Ravi");
    expect(report).toMatchObject({ sync_state: "submitted", server_decision: "AUTO_MATCHED", project_id: 7, server_event_id: 100 });
    expect(report.activity).toMatchObject({ activity_code: "PIP-L5-002", location: "R03" });
    expect(server.received).toHaveLength(1);
    expect(await store.getReport(report.local_id)).toMatchObject({ sync_state: "submitted" });
  });

  it("offline submit is persisted as queued, then sent when the server is back", async () => {
    const { queue, server, store, clock } = setup();
    server.offline = true;
    const report = await queue.submit(CONFIDENT, PROJECT, null);
    expect(report).toMatchObject({ sync_state: "queued", retry_count: 1 });
    expect(report.last_error).toMatch(/saved on this device/);
    expect(await store.getReport(report.local_id)).toMatchObject({ sync_state: "queued", text: CONFIDENT });

    server.offline = false;
    await queue.syncDue(); // not due yet: backoff respected
    expect(server.received).toHaveLength(0);
    clock.t += backoffMs(1);
    await queue.syncDue();
    expect(await store.getReport(report.local_id)).toMatchObject({ sync_state: "submitted", server_decision: "AUTO_MATCHED", last_error: null });
  });

  it("the queue survives an app restart, including a send interrupted mid-flight", async () => {
    const store = createMemoryStore();
    const first = setup(createFakeServer(), store);
    first.server.offline = true;
    const a = await first.queue.submit(CONFIDENT, PROJECT, null);
    await store.putReport({ ...(await store.getReport(a.local_id))!, sync_state: "syncing" }); // app killed while sending

    const second = setup(createFakeServer(), store); // new process, same on-device database
    await second.queue.recoverInterrupted();
    await second.queue.syncDue(true);
    expect(await store.getReport(a.local_id)).toMatchObject({ sync_state: "submitted" });
  });

  it("a lost reply is retried with the same client_report_id and does not duplicate the event", async () => {
    const { queue, server, clock } = setup();
    server.dropResponseOnce = true; // server stored the report, phone never got the answer
    const report = await queue.submit(CONFIDENT, PROJECT, null);
    expect(report.sync_state).toBe("queued");
    clock.t += backoffMs(1);
    await queue.syncDue();
    const ids = server.received.map((r) => r.client_report_id);
    expect(ids).toEqual([report.local_id, report.local_id]);
    expect(server.reports.size).toBe(1); // one event on the server
  });

  it("non-retryable errors fail immediately and keep the report", async () => {
    const { queue, server, store } = setup();
    server.failNext = [422];
    const report = await queue.submit(CONFIDENT, PROJECT, null);
    expect(report).toMatchObject({ sync_state: "failed" });
    expect(await store.getReport(report.local_id)).not.toBeNull();
    const retried = await queue.retry(report.local_id); // manual retry after fixing
    expect(retried).toMatchObject({ sync_state: "submitted" });
  });

  it("stops automatic retries after the budget and marks the report failed", async () => {
    const { queue, server, clock } = setup();
    server.failNext = Array(MAX_AUTO_RETRIES).fill(503);
    let report = await queue.submit(CONFIDENT, PROJECT, null);
    while (report.sync_state === "queued") {
      clock.t += backoffMs(report.retry_count);
      await queue.syncDue();
      report = (await queue.refresh(report.local_id))!;
    }
    expect(report).toMatchObject({ sync_state: "failed", retry_count: MAX_AUTO_RETRIES });
    expect(report.last_error).toMatch(/Automatic retries stopped/);
  });

  it("backoff grows exponentially and is capped", () => {
    expect([1, 2, 3, 4].map(backoffMs)).toEqual([5000, 10000, 20000, 40000]);
    expect(backoffMs(30)).toBe(300000);
  });

  it("concurrent sync calls never send the same report twice", async () => {
    const { queue, server, clock } = setup();
    server.offline = true;
    await queue.submit(CONFIDENT, PROJECT, null);
    await queue.submit("Pump CT103 installed at Unit 2, 50%.", PROJECT, null);
    server.offline = false;
    server.received = [];
    clock.t += backoffMs(1);
    await Promise.all([queue.syncDue(), queue.syncDue(), queue.syncDue(true)]);
    const ids = server.received.map((r) => r.client_report_id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toHaveLength(2);
  });

  it("only an explicit discard deletes an unsent report, and submitted reports cannot be discarded", async () => {
    const { queue, server, store } = setup();
    const sent = await queue.submit(CONFIDENT, PROJECT, null);
    server.offline = true;
    const unsent = await queue.submit("Pump CT103 installed at Unit 2, 50%.", PROJECT, null);
    await queue.discard(sent.local_id);
    await queue.discard(unsent.local_id);
    expect(await store.getReport(sent.local_id)).not.toBeNull();
    expect(await store.getReport(unsent.local_id)).toBeNull();
  });

  it("refresh picks up the planner's decision after confirmation in the web app", async () => {
    const { queue, server } = setup();
    const report = await queue.submit(CONFIDENT, PROJECT, null);
    expect((await queue.refresh(report.local_id))!.server_decision).toBe("AUTO_MATCHED");
    server.approve(report.server_event_id!);
    expect((await queue.refresh(report.local_id))!.server_decision).toBe("APPROVED");
  });
});
