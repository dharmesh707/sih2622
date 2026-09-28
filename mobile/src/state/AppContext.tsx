import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { createApiClient, validateBaseUrl, type ApiClient } from "../api/client";
import { getProjects } from "../api/endpoints";
import { ApiError, toApiError } from "../api/errors";
import { createQueue } from "../offline/queue";
import type { Store } from "../offline/store";
import { EMPTY_SHORTCUTS, type Shortcuts } from "../report";
import type { TokenStore } from "../storage/secureToken";
import type { LocalReport, Project } from "../types";

export interface AppDeps {
  store: Store;
  tokens: TokenStore;
  newId: () => string;
  isDeviceOnline: () => Promise<boolean>;
  onDeviceOnlineChange: (listener: (online: boolean) => void) => () => void;
  fetchImpl?: typeof fetch;
  syncIntervalMs?: number;
}

export type Connection = "connecting" | "online" | "offline" | "server_unavailable" | "unauthorized" | "not_configured";

export interface Draft {
  text: string;
  shortcuts: Shortcuts;
}

interface AppState {
  ready: boolean;
  baseUrl: string | null;
  workerName: string | null;
  hasToken: boolean;
  project: Project | null;
  projects: Project[];
  projectsCachedAt: string | null;
  projectsFromCache: boolean;
  connection: Connection;
  reports: LocalReport[];
}

const KEYS = { baseUrl: "base_url", workerName: "worker_name", project: "project", projects: "projects_cache", draft: (id: number) => `draft:${id}` };

function useAppModel(deps: AppDeps) {
  const { store, tokens } = deps;
  const [state, setState] = useState<AppState>({
    ready: false,
    baseUrl: null,
    workerName: null,
    hasToken: false,
    project: null,
    projects: [],
    projectsCachedAt: null,
    projectsFromCache: false,
    connection: "not_configured",
    reports: [],
  });
  // Actions read the latest state without being recreated on every render.
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  });
  const patch = useCallback((p: Partial<AppState>) => setState((s) => ({ ...s, ...p })), []);

  // One stable queue for the provider's lifetime; it reads the current API client lazily.
  const [engine] = useState(() => {
    let client: ApiClient | null = null;
    return {
      getClient: () => client,
      setClient: (next: ApiClient | null) => {
        client = next;
      },
      queue: createQueue({ store, api: () => client, newId: deps.newId }),
    };
  });
  const { queue } = engine;
  const makeClient = useCallback(
    (baseUrl: string | null) => engine.setClient(baseUrl ? createApiClient({ baseUrl, getToken: tokens.get, fetchImpl: deps.fetchImpl }) : null),
    [engine, tokens, deps.fetchImpl],
  );

  const reloadReports = useCallback(async () => patch({ reports: await store.listReports() }), [store, patch]);

  const cacheProjects = useCallback(
    async (list: Project[]) => {
      const cachedAt = new Date().toISOString();
      await store.setValue(KEYS.projects, JSON.stringify({ list, cachedAt }));
      const current = stateRef.current.project;
      const stillExists = current ? list.find((p) => p.id === current.id) ?? null : null;
      patch({ projects: list, projectsCachedAt: cachedAt, projectsFromCache: false, project: stillExists ?? current });
    },
    [store, patch],
  );

  // Device connectivity is not the same as the server being reachable, so both are checked.
  const checkServer = useCallback(async (): Promise<Connection> => {
    const deviceOnline = await deps.isDeviceOnline();
    const client = engine.getClient();
    let connection: Connection;
    if (!client || !stateRef.current.hasToken) connection = "not_configured";
    else if (!deviceOnline) connection = "offline";
    else {
      patch({ connection: "connecting" });
      try {
        await cacheProjects(await getProjects(client));
        connection = "online";
      } catch (error) {
        const e = toApiError(error);
        connection = e.status === 401 ? "unauthorized" : e.kind === "offline" ? "offline" : "server_unavailable";
      }
    }
    patch({ connection });
    return connection;
  }, [deps, engine, patch, cacheProjects]);

  const syncNow = useCallback(
    async (force = false) => {
      if ((await checkServer()) === "online") await queue.syncDue(force);
      await reloadReports();
    },
    [checkServer, queue, reloadReports],
  );

  // Startup: restore settings, recover interrupted sends, then try to sync. Never blocks on the server.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [baseUrl, workerName, projectJson, projectsJson, token] = await Promise.all([
        store.getValue(KEYS.baseUrl),
        store.getValue(KEYS.workerName),
        store.getValue(KEYS.project),
        store.getValue(KEYS.projects),
        tokens.get(),
      ]);
      const cache = projectsJson ? (JSON.parse(projectsJson) as { list: Project[]; cachedAt: string }) : null;
      makeClient(baseUrl);
      await queue.recoverInterrupted();
      if (cancelled) return;
      patch({
        ready: true,
        baseUrl,
        workerName,
        hasToken: Boolean(token),
        project: projectJson ? (JSON.parse(projectJson) as Project) : null,
        projects: cache?.list ?? [],
        projectsCachedAt: cache?.cachedAt ?? null,
        projectsFromCache: Boolean(cache),
        reports: await store.listReports(),
      });
    })();
    return () => {
      cancelled = true;
    };
  }, [store, tokens, queue, makeClient, patch]);

  useEffect(() => {
    if (!state.ready) return;
    let active = true;
    void deps.isDeviceOnline().then(() => {
      if (active) void syncNow();
    });
    const unsubscribe = deps.onDeviceOnlineChange((online) => {
      // Reconnecting ends the reason for waiting, so queued reports go out now rather than after backoff.
      if (online) void syncNow(true);
      else patch({ connection: "offline" });
    });
    const timer = setInterval(() => void syncNow(), deps.syncIntervalMs ?? 30_000);
    return () => {
      active = false;
      unsubscribe();
      clearInterval(timer);
    };
  }, [state.ready, state.baseUrl, state.hasToken, deps, syncNow, patch]);

  const actions = useMemo(
    () => ({
      // Saves the connection only after the server accepts the token.
      async saveConnection(urlInput: string, token: string, workerName: string): Promise<string | null> {
        const valid = validateBaseUrl(urlInput);
        if ("error" in valid) return valid.error;
        const newToken = token.trim();
        if (!newToken && !stateRef.current.hasToken) return "Enter the access token from your planner.";
        const previous = await tokens.get();
        const candidate = newToken || previous;
        const probe = createApiClient({ baseUrl: valid.url, getToken: async () => candidate, fetchImpl: deps.fetchImpl });
        let list: Project[];
        try {
          list = await getProjects(probe);
        } catch (error) {
          return error instanceof ApiError ? error.message : "Could not reach the server.";
        }
        if (newToken) await tokens.set(newToken);
        await store.setValue(KEYS.baseUrl, valid.url);
        const name = workerName.trim();
        if (name) await store.setValue(KEYS.workerName, name);
        else await store.deleteValue(KEYS.workerName);
        makeClient(valid.url);
        patch({ baseUrl: valid.url, workerName: name || null, hasToken: true, connection: "online" });
        await cacheProjects(list);
        return null;
      },

      async logout() {
        await tokens.clear();
        patch({ hasToken: false, connection: "not_configured" });
      },

      refreshProjects: checkServer,

      async selectProject(project: Project) {
        await store.setValue(KEYS.project, JSON.stringify(project));
        patch({ project });
      },

      async submit(text: string): Promise<LocalReport> {
        const { project, workerName } = stateRef.current;
        if (!project) throw new Error("Select a project first.");
        const report = await queue.submit(text, project, workerName);
        await store.deleteValue(KEYS.draft(project.id));
        await reloadReports();
        if (report.sync_state !== "submitted") void checkServer();
        return report;
      },

      async retry(localId: string) {
        const report = await queue.retry(localId);
        await reloadReports();
        return report;
      },

      async discard(localId: string) {
        await queue.discard(localId);
        await reloadReports();
      },

      syncNow,

      async refreshReport(localId: string) {
        try {
          const report = await queue.refresh(localId);
          await reloadReports();
          return report;
        } catch {
          return store.getReport(localId);
        }
      },

      async loadDraft(projectId: number): Promise<Draft> {
        const raw = await store.getValue(KEYS.draft(projectId));
        return raw ? (JSON.parse(raw) as Draft) : { text: "", shortcuts: EMPTY_SHORTCUTS };
      },

      async saveDraft(projectId: number, draft: Draft) {
        await store.setValue(KEYS.draft(projectId), JSON.stringify(draft));
      },

      async discardDraft(projectId: number) {
        await store.deleteValue(KEYS.draft(projectId));
      },
    }),
    [tokens, store, deps.fetchImpl, makeClient, patch, cacheProjects, checkServer, queue, reloadReports, syncNow],
  );

  return { ...state, ...actions };
}

export type AppModel = ReturnType<typeof useAppModel>;

const AppContext = createContext<AppModel | null>(null);

export function AppProvider({ deps, children }: { deps: AppDeps; children: ReactNode }) {
  const model = useAppModel(deps);
  return <AppContext.Provider value={model}>{children}</AppContext.Provider>;
}

export function useApp(): AppModel {
  const model = useContext(AppContext);
  if (!model) throw new Error("useApp must be used inside AppProvider");
  return model;
}
