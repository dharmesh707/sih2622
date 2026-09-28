import type { LocalReport } from "../types";

// Durable storage the queue depends on. The app uses the SQLite implementation (storage/sqlite.ts);
// tests use the in-memory one below.
export interface Store {
  listReports(): Promise<LocalReport[]>;
  getReport(localId: string): Promise<LocalReport | null>;
  putReport(report: LocalReport): Promise<void>;
  deleteReport(localId: string): Promise<void>;
  getValue(key: string): Promise<string | null>;
  setValue(key: string, value: string): Promise<void>;
  deleteValue(key: string): Promise<void>;
}

export function createMemoryStore(): Store {
  const reports = new Map<string, LocalReport>();
  const values = new Map<string, string>();
  const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v));
  return {
    listReports: async () => [...reports.values()].map(clone).sort((a, b) => b.created_at.localeCompare(a.created_at)),
    getReport: async (id) => (reports.has(id) ? clone(reports.get(id)!) : null),
    putReport: async (r) => void reports.set(r.local_id, clone(r)),
    deleteReport: async (id) => void reports.delete(id),
    getValue: async (k) => values.get(k) ?? null,
    setValue: async (k, v) => void values.set(k, v),
    deleteValue: async (k) => void values.delete(k),
  };
}
