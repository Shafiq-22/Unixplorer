import { describe, expect, it } from "vitest";
import { fetchHealth, parseHealth } from "./health";

const valid = {
  status: "ok",
  api_version: "0.1.0",
  database: { reachable: true, migration_revision: "0001", error: null },
  snapshot: { ingestion_job_id: 2, finished_at: "2026-10-12T11:00:50Z", datasets: { a: "b" } },
  frame: { galactocentric_defaults: "v4.0", astropy_version: "8.0.1" },
};

describe("parseHealth", () => {
  it("accepts a well-formed response", () => {
    expect(parseHealth(valid).kind).toBe("ok");
  });

  it("rejects a response that does not match the schema", () => {
    expect(parseHealth({ ...valid, status: "fine" }).kind).toBe("invalid");
    expect(parseHealth({ status: "ok" }).kind).toBe("invalid");
  });
});

describe("fetchHealth", () => {
  it("reports an unreachable API instead of throwing", async () => {
    const failing = (() => Promise.reject(new Error("ECONNREFUSED"))) as typeof fetch;
    expect(await fetchHealth("http://127.0.0.1:1", failing)).toEqual({
      kind: "unreachable",
      reason: "API not reachable",
    });
  });

  it("reports HTTP errors", async () => {
    const http500 = (() => Promise.resolve(new Response("x", { status: 500 }))) as typeof fetch;
    expect((await fetchHealth("http://api", http500)).kind).toBe("unreachable");
  });
});
