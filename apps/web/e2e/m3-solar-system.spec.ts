import { expect, test, type Page } from "@playwright/test";

// M3: Horizons bodies at the snapshot epoch (shown in the UI), seamless zoom from planetary
// orbits to stellar distances, and routes starting from Earth.

async function pick(page: Page, query: string, name: string) {
  const box = page.getByTestId("search");
  await box.fill(query);
  await expect(page.getByRole("option").first()).toContainText(name);
  await box.press("Enter");
  await expect(page.getByTestId("dossier").getByRole("heading", { level: 2 })).toHaveText(name);
}

test("snapshot epoch and Solar System bodies are shown", async ({ page }) => {
  await page.goto("/");
  const ss = page.getByTestId("solar-system");
  await expect(ss.getByTestId("snapshot-epoch")).toContainText("JD 2457389.0 TDB");
  await expect(ss.getByTestId("snapshot-epoch")).toContainText("A.D. 2016-Jan-01 12:00:00.0000 TDB");
  const mars = ss.getByRole("row").filter({ hasText: "Mars" });
  await expect(mars).toContainText("AU");
  await expect(mars).toContainText("derived");
  await expect(mars).toContainText("mar099"); // per-body ephemeris source from Horizons
  // At planetary scale every body is labelled; overlapping ones share a label.
  await expect(page.locator(".body-label", { hasText: "Sun" })).toBeVisible();
  await expect(page.locator(".body-label", { hasText: "Jupiter" })).toBeVisible();
});

test("route from Earth to Mars uses planetary units", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("route-origin")).toHaveText("Earth");
  await pick(page, "mars", "Mars");
  await page.getByTestId("dossier").getByTestId("set-destination").click();
  await page.getByTestId("calculate").click();
  const results = page.getByTestId("route-results");
  await expect(results.getByTestId("route-distance")).toContainText("AU");
  // Light time between planets is minutes, not years.
  await expect(results.locator('tr[data-model="null_propagation"] td').first()).toHaveText(/ (s|h)$/);
});

test("route from Earth to Proxima Centauri", async ({ page }) => {
  await page.goto("/");
  await pick(page, "proxima", "Proxima Centauri");
  await page.getByTestId("dossier").getByTestId("set-destination").click();
  await page.getByTestId("calculate").click();
  const results = page.getByTestId("route-results");
  await expect(results.getByTestId("route-distance")).toContainText("pc");
  await expect(results).toContainText("Earth → Proxima Centauri");
});

async function cameraPc(page: Page): Promise<number> {
  return Number(await page.getByTestId("view-radius").getAttribute("data-pc"));
}

test("seamless zoom from Earth-Moon scale to stellar distances", async ({ page }) => {
  await page.goto("/");
  await pick(page, "earth", "Earth");
  await page.getByTestId("dossier").getByRole("button", { name: "Focus in 3D" }).click();
  const start = await cameraPc(page);
  // Each click zooms 4x: six clicks bring the camera ~4096x closer, to about 7e-8 pc,
  // where Earth and Moon (~1.3e-8 pc apart) are resolved with separate labels.
  for (let i = 0; i < 6; i++) await page.getByTestId("zoom-in").click();
  expect(await cameraPc(page)).toBeCloseTo(start / 4 ** 6, 12);
  await expect(page.getByTestId("view-radius")).toContainText("AU");
  await expect(page.locator(".body-label", { hasText: /^Moon$/ })).toBeVisible();
  await expect(page.locator(".body-label", { hasText: /^Earth$/ })).toBeVisible();
  // Out to stellar distances in the same view, no reload.
  for (let i = 0; i < 12; i++) await page.getByTestId("zoom-out").click();
  expect(await cameraPc(page)).toBeGreaterThan(1);
  await expect(page.getByTestId("view-radius")).toContainText("pc");
  await expect(page.locator(".body-label")).toHaveCount(0); // labels hidden at stellar scale
  await expect(page.locator("canvas")).toBeVisible();
});
