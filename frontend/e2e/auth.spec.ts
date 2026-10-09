import { test, expect } from "@playwright/test";

test("authentication pages render", async ({ page }) => {
  await page.goto("/auth/login");
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await page.goto("/auth/register");
  await expect(page.getByRole("heading", { name: "Create account" })).toBeVisible();
});

test.describe("live auth", () => {
  test.skip(!process.env.E2E_LIVE_AUTH, "requires a running backend stack");

  test("a user can register then log in through the frontend proxy", async ({ page }) => {
    const email = `e2e-${Date.now()}@example.com`;
    const password = "e2e-test-password";

    await page.goto("/auth/register");
    await page.getByPlaceholder("Email").fill(email);
    await page.getByPlaceholder("Password").fill(password);
    await page.getByRole("button", { name: "Register" }).click();
    await expect(page.getByText("Success.")).toBeVisible();

    await page.goto("/auth/login");
    await page.getByPlaceholder("Email").fill(email);
    await page.getByPlaceholder("Password").fill(password);
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page.getByText("Success.")).toBeVisible();
  });
});
