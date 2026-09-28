import { userEvent } from "@testing-library/react-native";
import { renderRouter, screen } from "expo-router/testing-library";
import { useState } from "react";

import Home from "../src/app/home";
import Index from "../src/app/index";
import Pending from "../src/app/pending";
import Projects from "../src/app/projects";
import Record from "../src/app/record";
import ReportDetail from "../src/app/report/[id]";
import Reports from "../src/app/reports";
import Result from "../src/app/result/[id]";
import Settings from "../src/app/settings";
import Setup from "../src/app/setup";
import { AppShell } from "../src/components/AppShell";
import { createMemoryStore, type Store } from "../src/offline/store";
import type { AppDeps } from "../src/state/AppContext";
import { createMemoryTokenStore, type TokenStore } from "../src/storage/secureToken";
import { createFakeServer, PROJECT, TOKEN, type FakeServer } from "./fakeServer";

const CONFIDENT = "Piping crew completed spool XX102 at rack 3, 100%.";

interface Env {
  server: FakeServer;
  store: Store;
  tokens: TokenStore;
  device: { online: boolean; emit: (online: boolean) => void };
}

function makeEnv(): Env {
  const listeners = new Set<(online: boolean) => void>();
  const device = {
    online: true,
    emit(online: boolean) {
      device.online = online;
      listeners.forEach((l) => l(online));
    },
  };
  const env: Env = { server: createFakeServer(), store: createMemoryStore(), tokens: createMemoryTokenStore(), device };
  let n = 0;
  const deps: AppDeps = {
    store: env.store,
    tokens: env.tokens,
    newId: () => `local-${String(++n).padStart(6, "0")}`,
    isDeviceOnline: async () => device.online,
    onDeviceOnlineChange: (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    fetchImpl: env.server.fetch,
    syncIntervalMs: 60 * 60_000,
  };
  (env as Env & { deps: AppDeps }).deps = deps;
  return env;
}

// An already-configured phone: server address, token in secure storage, project selected.
async function configured(env: Env) {
  await env.store.setValue("base_url", "https://progresssync.example.com");
  await env.store.setValue("project", JSON.stringify(PROJECT));
  await env.tokens.set(TOKEN);
}

function renderApp(env: Env, initialUrl = "/") {
  const deps = (env as Env & { deps: AppDeps }).deps;
  function TestLayout() {
    const [stableDeps] = useState(deps);
    return <AppShell deps={stableDeps} />;
  }
  return renderRouter(
    {
      _layout: TestLayout,
      index: Index,
      setup: Setup,
      projects: Projects,
      home: Home,
      record: Record,
      "result/[id]": Result,
      reports: Reports,
      "report/[id]": ReportDetail,
      pending: Pending,
      settings: Settings,
    },
    { initialUrl },
  );
}

async function submitReport(text: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("What happened on site?"), text);
  await user.press(screen.getByRole("button", { name: `Submit to ${PROJECT.name}` }));
}

describe("ground worker flows", () => {
  it("A. online: setup → project → record → submit → actual server result", async () => {
    const env = makeEnv();
    const user = userEvent.setup();
    await renderApp(env);

    await user.type(await screen.findByLabelText("Server address"), "https://progresssync.example.com");
    await user.type(screen.getByLabelText("Access token"), TOKEN);
    await user.type(screen.getByLabelText("Your name (optional, stays on this phone)"), "Ravi");
    await user.press(screen.getByRole("button", { name: "Save and connect" }));

    await user.press(await screen.findByRole("button", { name: `Project ${PROJECT.name}` }));
    await user.press(await screen.findByRole("button", { name: "Record Field Update" }));
    await submitReport(CONFIDENT);

    expect(await screen.findByText("Sent to ProgressSync")).toBeOnTheScreen();
    expect(screen.getByText("Matched — awaiting planner confirmation")).toBeOnTheScreen();
    expect(screen.getByText("PIP-L5-002")).toBeOnTheScreen();
    expect(screen.getByText(/Planner confirmation required/)).toBeOnTheScreen();
    expect(screen.queryByText("Schedule updated")).not.toBeOnTheScreen();
    expect(env.server.received).toEqual([{ project_id: 7, text: CONFIDENT, source: "mobile", client_report_id: "local-000001" }]);
    expect(await env.tokens.get()).toBe(TOKEN);
    expect(await env.store.getValue("base_url")).toBe("https://progresssync.example.com");
  });

  it("A2. a wrong token is refused at setup with a clear message", async () => {
    const env = makeEnv();
    const user = userEvent.setup();
    await renderApp(env);
    await user.type(await screen.findByLabelText("Server address"), "https://progresssync.example.com");
    await user.type(screen.getByLabelText("Access token"), "not-the-token");
    await user.press(screen.getByRole("button", { name: "Save and connect" }));
    expect(await screen.findByText("Your connection token is invalid. Open Settings to update it.")).toBeOnTheScreen();
    expect(await env.tokens.get()).toBeNull();
  });

  it("B. offline: submit → saved offline → reconnect → submitted", async () => {
    const env = makeEnv();
    await configured(env);
    env.device.online = false;
    env.server.offline = true;
    await renderApp(env, "/record");

    await submitReport(CONFIDENT);
    expect(await screen.findByText("Saved on this phone")).toBeOnTheScreen();
    expect(screen.getByText("Saved offline — waiting for connection")).toBeOnTheScreen();
    expect(screen.getByText("Not sent yet — stored only on this device")).toBeOnTheScreen();
    expect((await env.store.listReports())[0]).toMatchObject({ sync_state: "queued", text: CONFIDENT });

    env.server.offline = false;
    env.device.emit(true); // connectivity returns → queue syncs
    expect(await screen.findByText("Sent to ProgressSync")).toBeOnTheScreen();
    expect(screen.getByText("Matched — awaiting planner confirmation")).toBeOnTheScreen();
    expect(env.server.reports.size).toBe(1);
  });

  it("C. review: REVIEW_REQUIRED shows planner review, never 'Schedule updated'", async () => {
    const env = makeEnv();
    await configured(env);
    await renderApp(env, "/record");
    await submitReport("Pump CT103 installed at Unit 2, 50%.");
    expect(await screen.findByText("Review required")).toBeOnTheScreen();
    expect(screen.getByText(/A planner will choose the right activity/)).toBeOnTheScreen();
    expect(screen.queryByText("Schedule updated")).not.toBeOnTheScreen();
  });

  it("D. unmatched: the observation is preserved on the server with no activity", async () => {
    const env = makeEnv();
    await configured(env);
    await renderApp(env, "/record");
    await submitReport("ZZ-999 unknown activity at offshore platform, 20%.");
    expect(await screen.findByText("Unmatched — observation saved")).toBeOnTheScreen();
    expect(screen.getByText(/Report #100 · Event #100/)).toBeOnTheScreen();
    expect(screen.queryByText("Matched to")).not.toBeOnTheScreen();
  });

  it("E. retry: server error → queued → Sync now in Pending → submitted", async () => {
    const env = makeEnv();
    await configured(env);
    env.server.failNext = [503];
    const user = userEvent.setup();
    await renderApp(env, "/record");

    await submitReport(CONFIDENT);
    expect(await screen.findByText("Saved on this phone")).toBeOnTheScreen();
    expect(screen.getByText("Saved offline — waiting for connection")).toBeOnTheScreen();
    expect(screen.getByText(/temporarily unavailable\. Your report has not been written to the schedule/)).toBeOnTheScreen();

    await user.press(screen.getByRole("button", { name: "Home" }));
    await user.press(await screen.findByRole("button", { name: "Pending Sync (1)" }));
    await user.press(await screen.findByRole("button", { name: "Sync now" }));
    expect(await screen.findByText("Everything on this phone has been sent.")).toBeOnTheScreen();
    expect(env.server.received.map((r) => r.client_report_id)).toEqual(["local-000001", "local-000001"]);
  });

  it("the draft survives leaving the screen and uses the selected project", async () => {
    const env = makeEnv();
    await configured(env);
    const user = userEvent.setup();
    await renderApp(env, "/record");
    await user.type(await screen.findByLabelText("What happened on site?"), "Spool XX102 half done");
    await user.press(screen.getByRole("button", { name: "50%" }));
    expect(screen.getByLabelText("Final report text")).toHaveTextContent("Spool XX102 half done, 50%.");
    expect(JSON.parse((await env.store.getValue(`draft:${PROJECT.id}`))!)).toMatchObject({ text: "Spool XX102 half done" });
  });

  it("report detail shows 'Schedule updated' only after the planner approves", async () => {
    const env = makeEnv();
    await configured(env);
    const user = userEvent.setup();
    await renderApp(env, "/record");
    await submitReport(CONFIDENT);
    await screen.findByText("Sent to ProgressSync");
    env.server.approve(100); // planner confirms in the web app

    await user.press(screen.getByRole("button", { name: "Home" }));
    await user.press(await screen.findByRole("button", { name: "My Reports (1)" }));
    await user.press(await screen.findByRole("button", { name: /^Report: Piping crew/ }));
    expect(await screen.findByText("Schedule updated")).toBeOnTheScreen();
    expect(screen.getByText("Updated activity")).toBeOnTheScreen();
  });
});
