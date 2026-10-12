import { expect, test, type Page } from "@playwright/test";

// M2 milestone path: search -> dossier -> 3D view centred on the Sun -> route Sun -> Proxima
// -> travel with all model results side by side -> pause, resume and cancel.

async function pick(page: Page, query: string, name: string) {
  const box = page.getByTestId("search");
  await box.fill(query);
  await expect(page.getByRole("option").first()).toContainText(name);
  await box.press("Enter"); // keyboard alternative to clicking
  await expect(page.getByTestId("dossier").getByRole("heading", { level: 2 })).toHaveText(name);
}

async function coordinateTime(page: Page): Promise<number> {
  return Number(await page.getByTestId("coordinate-time").getAttribute("data-years"));
}

test("search, dossier, route Sun -> Proxima, travel, pause/resume/cancel", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("canvas")).toBeVisible();
  // Earth is the default origin (M3: routes start from Earth).
  await expect(page.getByTestId("route-origin")).toHaveText("Earth");

  await pick(page, "proxima", "Proxima Centauri");
  const dossier = page.getByTestId("dossier");
  const parallax = dossier.locator('tr[data-quantity="parallax"]');
  await expect(parallax).toContainText("mas");
  await expect(parallax).toContainText("1σ");
  await expect(parallax).toContainText("measured");
  await expect(dossier.getByTestId("distance")).toContainText("pc");
  await expect(dossier.getByTestId("distance")).toContainText("published estimate");
  await expect(dossier.getByTestId("distance")).toContainText("bailer_jones_2021_geometric");

  await dossier.getByTestId("set-destination").click();
  await expect(page.getByTestId("route-destination")).toHaveText("Proxima Centauri");

  await page.getByTestId("speed").fill("0.5");
  await page.getByTestId("calculate").click();
  const results = page.getByTestId("route-results");
  await expect(results).toBeVisible();
  await expect(results.getByTestId("route-distance")).toContainText("pc");
  for (const model of [
    "classical_constant_speed",
    "sr_inertial",
    "sr_constant_proper_accel",
    "null_propagation",
    "hypothetical_ftl_effective",
  ]) {
    await expect(results.locator(`tr[data-model="${model}"]`)).toBeVisible();
  }
  await expect(results.locator('tr[data-model="hypothetical_ftl_effective"]')).toContainText("Speculative");
  await expect(results.locator('tr[data-model="null_propagation"]')).toContainText("not defined");

  await page.getByTestId("travel").click();
  const status = page.getByTestId("traversal-status");
  await expect(status).toHaveText("running");
  await expect.poll(() => coordinateTime(page)).toBeGreaterThan(0);

  await page.getByTestId("pause").click();
  await expect(status).toHaveText("paused");
  const paused = await coordinateTime(page);
  await page.waitForTimeout(700);
  expect(await coordinateTime(page)).toBe(paused);

  await page.getByTestId("resume").click();
  await expect(status).toHaveText("running");
  await expect.poll(() => coordinateTime(page)).toBeGreaterThan(paused);

  await page.getByTestId("cancel").click();
  await expect(status).toHaveText("cancelled");
  const cancelled = await coordinateTime(page);
  await page.waitForTimeout(500);
  expect(await coordinateTime(page)).toBe(cancelled);
});

test("objects without a distance stay sky-only and cannot be routed", async ({ page }) => {
  await page.goto("/");
  await pick(page, "sgr a", "Sgr A* (Galactic Centre)");
  const dossier = page.getByTestId("dossier");
  await expect(dossier).toContainText("sky view only");
  await expect(dossier.getByTestId("set-destination")).toBeDisabled();
});

test("health page reports the loaded snapshot", async ({ page }) => {
  await page.goto("/health");
  await expect(page.getByText("ok", { exact: true })).toBeVisible();
  await expect(page.getByText("gaia_dr3_nearby")).toBeVisible();
});
