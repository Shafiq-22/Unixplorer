import { z } from "zod";
import type {
  Dossier,
  ModelEntry,
  RouteResult,
  SearchResults,
  StarTile,
  Trajectory,
  Traversal,
} from "@atlas/shared-types";

// Zod at the trust boundary (CLAUDE.md §14). Each schema `satisfies` the type generated from
// the API's OpenAPI schema, so a drift between the two fails typecheck.

const publication = z.object({ bibcode: z.string(), citation: z.string().nullable() });

const sourceRef = z.object({
  source_record_id: z.string(),
  dataset: z.string(),
  archive: z.string(),
  release: z.string(),
  retrieved_at: z.string(),
  publication: publication.nullable().optional(),
});

const objectSummary = z.object({
  id: z.number().int(),
  primary_name: z.string(),
  display_name: z.string(),
  object_type: z.string(),
  has_3d_position: z.boolean(),
  matched_alias: z.string().nullable().optional(),
});

export const searchResultsSchema = z.object({
  query: z.string(),
  results: z.array(objectSummary),
}) satisfies z.ZodType<SearchResults>;

const measurement = z.object({
  quantity: z.string(),
  value: z.number().nullable(),
  unit: z.string(),
  uncertainty: z
    .object({ lower: z.number().nullable(), upper: z.number().nullable(), type: z.string() })
    .nullable(),
  state: z.string(),
  method: z.string(),
  solution_key: z.string().nullable(),
  is_default: z.boolean().nullable(),
  source: sourceRef,
});

const position = z.object({
  id: z.number().int(),
  kind: z.enum(["sky", "state_vector"]),
  frame: z.string(),
  epoch: z.string(),
  ra_deg: z.number().nullable(),
  dec_deg: z.number().nullable(),
  ra_error_mas: z.number().nullable(),
  dec_error_mas: z.number().nullable(),
  position_state: z.string(),
  position_method: z.string(),
  distance_state: z.string(),
  distance: z
    .object({
      value_pc: z.number(),
      lower_pc: z.number().nullable(),
      upper_pc: z.number().nullable(),
      interval: z.string().nullable(),
      method: z.string(),
      state: z.string(),
      source: sourceRef,
    })
    .nullable(),
  state_vector: z
    .object({
      x_km: z.number(),
      y_km: z.number(),
      z_km: z.number(),
      vx_km_s: z.number(),
      vy_km_s: z.number(),
      vz_km_s: z.number(),
    })
    .nullable(),
  cartesian: z
    .object({
      x_pc: z.number(),
      y_pc: z.number(),
      z_pc: z.number(),
      state: z.literal("derived"),
      method: z.string(),
    })
    .nullable(),
  source: sourceRef,
});

export const dossierSchema = z.object({
  object: objectSummary,
  identifiers: z.array(
    z.object({ catalogue: z.string(), identifier: z.string(), source_record_id: z.string() }),
  ),
  aliases: z.array(z.string()),
  classifications: z.array(
    z.object({ scheme: z.string(), value: z.string(), source_record_id: z.string() }),
  ),
  measurements: z.array(measurement),
  positions: z.array(position),
  parent: z.object({ object: objectSummary, reason: z.string() }).nullable(),
  children: z.array(objectSummary),
}) satisfies z.ZodType<Dossier>;

export const starTileSchema = z.object({
  level: z.number().int(),
  ix: z.number().int(),
  iy: z.number().int(),
  iz: z.number().int(),
  bounds_pc: z.array(z.number()).nullable(),
  frame: z.string(),
  complete: z.boolean(),
  total_in_cell: z.number().int(),
  stars: z.array(
    z.object({
      id: z.number().int(),
      x_pc: z.number(),
      y_pc: z.number(),
      z_pc: z.number(),
      phot_g_mean_mag: z.number().nullable(),
    }),
  ),
}) satisfies z.ZodType<StarTile>;

const quantityValue = z.object({ value: z.number(), unit: z.string() });
const modelOutput = z.union([quantityValue, z.number(), z.string()]);

const modelEntry = z.object({
  model_id: z.string(),
  model_version: z.string().nullable().optional(),
  status: z.enum(["physical", "speculative"]).nullable().optional(),
  inputs: z.record(z.string(), modelOutput).nullable().optional(),
  outputs: z.record(z.string(), modelOutput).nullable().optional(),
  assumptions: z.array(z.string()),
  warnings: z.array(z.string()),
  at_distance_lower: z.record(z.string(), quantityValue).nullable().optional(),
  at_distance_upper: z.record(z.string(), quantityValue).nullable().optional(),
  refused: z.string().nullable().optional(),
}) satisfies z.ZodType<ModelEntry>;

const routeEndpoint = z.object({
  object: objectSummary,
  position_id: z.number().int(),
  epoch: z.string(),
  position_method: z.string(),
  distance_method: z.string().nullable(),
});

export const routeResultSchema = z.object({
  id: z.number().int(),
  origin: routeEndpoint,
  destination: routeEndpoint,
  distance: z.object({
    value_pc: z.number(),
    lower_pc: z.number(),
    upper_pc: z.number(),
    method: z.string(),
  }),
  parameters: z.object({
    origin_id: z.number().int(),
    destination_id: z.number().int(),
    speed_fraction_c: z.number(),
    proper_acceleration_g: z.number(),
    ftl_speed_fraction_c: z.number(),
  }),
  frame: z.record(z.string(), z.unknown()),
  models: z.array(modelEntry),
  code_version: z.string(),
}) satisfies z.ZodType<RouteResult>;

export const trajectorySchema = z.object({
  route_id: z.number().int(),
  model_id: z.string(),
  model_version: z.string(),
  status: z.enum(["physical", "speculative"]),
  proper_time_defined: z.boolean(),
  samples: z.array(
    z.object({
      coordinate_time_yr: z.number(),
      proper_time_yr: z.number().nullable(),
      fraction: z.number(),
      speed_c: z.number(),
    }),
  ),
}) satisfies z.ZodType<Trajectory>;

export const traversalSchema = z.object({
  id: z.number().int(),
  route_id: z.number().int(),
  model_id: z.string(),
  status: z.enum(["planned", "running", "paused", "cancelled", "arrived"]),
  coordinate_time_yr: z.number(),
}) satisfies z.ZodType<Traversal>;
