import * as SQLite from "expo-sqlite";

import type { Store } from "../offline/store";
import type { LocalReport } from "../types";

// Reports and small settings live in an on-device SQLite file, so the queue survives app restarts.
export async function openSqliteStore(name = "progresssync-field.db"): Promise<Store> {
  const db = await SQLite.openDatabaseAsync(name);
  await db.execAsync(`
    PRAGMA journal_mode = WAL;
    CREATE TABLE IF NOT EXISTS reports (local_id TEXT PRIMARY KEY NOT NULL, created_at TEXT NOT NULL, json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL);
  `);
  return {
    async listReports() {
      const rows = await db.getAllAsync<{ json: string }>("SELECT json FROM reports ORDER BY created_at DESC");
      return rows.map((row) => JSON.parse(row.json) as LocalReport);
    },
    async getReport(localId) {
      const row = await db.getFirstAsync<{ json: string }>("SELECT json FROM reports WHERE local_id = ?", [localId]);
      return row ? (JSON.parse(row.json) as LocalReport) : null;
    },
    async putReport(report) {
      await db.runAsync("INSERT OR REPLACE INTO reports (local_id, created_at, json) VALUES (?, ?, ?)", [report.local_id, report.created_at, JSON.stringify(report)]);
    },
    async deleteReport(localId) {
      await db.runAsync("DELETE FROM reports WHERE local_id = ?", [localId]);
    },
    async getValue(key) {
      const row = await db.getFirstAsync<{ value: string }>("SELECT value FROM kv WHERE key = ?", [key]);
      return row?.value ?? null;
    },
    async setValue(key, value) {
      await db.runAsync("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", [key, value]);
    },
    async deleteValue(key) {
      await db.runAsync("DELETE FROM kv WHERE key = ?", [key]);
    },
  };
}
