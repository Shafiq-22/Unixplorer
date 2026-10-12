import { z } from "zod";
import type { Health } from "@atlas/shared-types";

// Zod at the trust boundary (CLAUDE.md §14). `satisfies` ties the runtime schema to the types
// generated from the API's OpenAPI schema, so a drift between them fails typecheck.
export const healthSchema = z.object({
  status: z.enum(["ok", "degraded"]),
  api_version: z.string(),
  database: z.object({
    reachable: z.boolean(),
    migration_revision: z.string().nullable(),
    error: z.string().nullable().optional(),
  }),
  snapshot: z
    .object({
      ingestion_job_id: z.number().int(),
      finished_at: z.string(),
      datasets: z.record(z.string(), z.string()),
    })
    .nullable(),
  frame: z.object({
    galactocentric_defaults: z.string(),
    astropy_version: z.string(),
  }),
}) satisfies z.ZodType<Health>;

export type HealthResult =
  | { kind: "ok"; health: Health }
  | { kind: "unreachable"; reason: string }
  | { kind: "invalid"; reason: string };

export function parseHealth(body: unknown): HealthResult {
  const parsed = healthSchema.safeParse(body);
  if (!parsed.success) {
    return { kind: "invalid", reason: "API response did not match the Health schema" };
  }
  return { kind: "ok", health: parsed.data };
}

export async function fetchHealth(apiUrl: string, fetcher: typeof fetch = fetch): Promise<HealthResult> {
  try {
    const res = await fetcher(`${apiUrl.replace(/\/$/, "")}/health`, { cache: "no-store" });
    if (!res.ok) {
      return { kind: "unreachable", reason: `API answered HTTP ${res.status}` };
    }
    return parseHealth(await res.json());
  } catch {
    return { kind: "unreachable", reason: "API not reachable" };
  }
}
