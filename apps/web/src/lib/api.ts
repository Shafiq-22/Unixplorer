import type { z } from "zod";
import type {
  Dossier,
  RouteRequest,
  RouteResult,
  SearchResults,
  StarTile,
  Trajectory,
  Traversal,
  TraversalUpdate,
} from "@atlas/shared-types";
import {
  dossierSchema,
  routeResultSchema,
  searchResultsSchema,
  starTileSchema,
  trajectorySchema,
  traversalSchema,
} from "./schemas";

// Browser code calls same-origin /api/*, which next.config.ts rewrites to the FastAPI server.
const BASE = "/api";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body && typeof body.detail === "string"
        ? body.detail
        : `HTTP ${res.status}`;
    throw new ApiError(detail, res.status);
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new ApiError(`response from ${path} did not match its schema`, res.status);
  }
  return parsed.data;
}

export const api = {
  search: (q: string): Promise<SearchResults> =>
    request(`/objects/search?q=${encodeURIComponent(q)}&limit=12`, searchResultsSchema),
  dossier: (id: number): Promise<Dossier> => request(`/objects/${id}`, dossierSchema),
  tile: (level: number, ix: number, iy: number, iz: number, limit = 3000): Promise<StarTile> =>
    request(`/stars/tiles/${level}/${ix}/${iy}/${iz}?limit=${limit}`, starTileSchema),
  createRoute: (req: RouteRequest): Promise<RouteResult> =>
    request("/routes", routeResultSchema, { method: "POST", body: JSON.stringify(req) }),
  trajectory: (routeId: number, modelId: string, samples = 400): Promise<Trajectory> =>
    request(
      `/routes/${routeId}/trajectory?model_id=${encodeURIComponent(modelId)}&samples=${samples}`,
      trajectorySchema,
    ),
  startTraversal: (routeId: number, modelId: string): Promise<Traversal> =>
    request("/traversals", traversalSchema, {
      method: "POST",
      body: JSON.stringify({ route_id: routeId, model_id: modelId }),
    }),
  updateTraversal: (id: number, update: TraversalUpdate): Promise<Traversal> =>
    request(`/traversals/${id}`, traversalSchema, {
      method: "PATCH",
      body: JSON.stringify(update),
    }),
};
