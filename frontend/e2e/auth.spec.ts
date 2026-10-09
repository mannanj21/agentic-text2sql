import { test, expect } from "@playwright/test";

test("authentication pages render", async ({ page }) => {
  await page.goto("/auth/login");
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await page.goto("/auth/register");
  await expect(page.getByRole("heading", { name: "Create account" })).toBeVisible();
});
