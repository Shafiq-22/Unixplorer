import { defineConfig, devices } from "@playwright/test";

// E2E of the M2 path (CLAUDE.md §10-§11) against the real API, database and web app.
// Needs a loaded database in DATABASE_URL. Set PLAYWRIGHT_CHROMIUM_EXECUTABLE to use a
// preinstalled Chromium instead of `playwright install chromium`.
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
const apiPort = 8000;
const webPort = 3000;

export default defineConfig({
  testDir: "e2e",
  timeout: 90_000,
  expect: { timeout: 20_000 },
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: executablePath ? { executablePath } : {},
      },
    },
  ],
  webServer: [
    {
      command: `uv run fastapi run services/api/main.py --port ${apiPort}`,
      cwd: "../..",
      url: `http://127.0.0.1:${apiPort}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: `pnpm start --port ${webPort}`,
      url: `http://127.0.0.1:${webPort}/health`,
      env: { ATLAS_API_URL: `http://127.0.0.1:${apiPort}` },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
