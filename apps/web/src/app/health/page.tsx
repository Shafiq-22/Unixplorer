import { fetchHealth } from "@/lib/health";

// Rendered per request: health must never be served from a build-time cache.
export const dynamic = "force-dynamic";

export default async function HealthPage() {
  const apiUrl = process.env.ATLAS_API_URL ?? "http://127.0.0.1:8000";
  const result = await fetchHealth(apiUrl);

  return (
    <main>
      <h1>Universe Atlas</h1>
      <p className="lede">Milky Way edition. System health (milestone M1: no explorer yet).</p>

      {result.kind !== "ok" ? (
        <p>
          <span className="badge bad">API {result.kind}</span> {result.reason}
        </p>
      ) : (
        <>
          <p>
            <span className={`badge ${result.health.status === "ok" ? "ok" : "warn"}`}>
              {result.health.status}
            </span>{" "}
            API {result.health.api_version}
          </p>

          <section aria-labelledby="db">
            <h2 id="db">Database</h2>
            <dl>
              <dt>Reachable</dt>
              <dd>{result.health.database.reachable ? "yes" : `no (${result.health.database.error ?? "unknown"})`}</dd>
              <dt>Migration</dt>
              <dd>{result.health.database.migration_revision ?? "none"}</dd>
            </dl>
          </section>

          <section aria-labelledby="snap">
            <h2 id="snap">Data snapshot</h2>
            {result.health.snapshot ? (
              <dl>
                <dt>Loaded by job</dt>
                <dd>#{result.health.snapshot.ingestion_job_id} at {result.health.snapshot.finished_at}</dd>
                {Object.entries(result.health.snapshot.datasets)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([dataset, retrieved]) => (
                    <div key={dataset} style={{ display: "contents" }}>
                      <dt>{dataset}</dt>
                      <dd>retrieved {retrieved}</dd>
                    </div>
                  ))}
              </dl>
            ) : (
              <p>No snapshot loaded. Run <code>uv run atlas db load</code>.</p>
            )}
          </section>

          <section aria-labelledby="frame">
            <h2 id="frame">Reference frame</h2>
            <dl>
              <dt>Galactocentric parameters</dt>
              <dd>astropy {result.health.frame.galactocentric_defaults} (astropy {result.health.frame.astropy_version})</dd>
            </dl>
          </section>
        </>
      )}
    </main>
  );
}
