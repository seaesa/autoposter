import { expect, test } from "@playwright/test"

test("dashboard shows and channels nav works", async ({ page }) => {
  await page.route("**/api/v1/tiktok-channels", (route) =>
    route.fulfill({
      json: [
        {
          id: 1,
          username: "demo",
          display_name: null,
          last_checked_at: null,
          backfill_anchor_video_id: null,
          backfill_remaining: 0,
          is_active: true,
          pages: [],
        },
      ],
    }),
  )
  await page.route("**/api/v1/stats", (route) =>
    route.fulfill({
      json: { today_posted: 3, today_pending: 1, channels: 1, scheduler: {} },
    }),
  )
  await page.route("**/api/v1/jobs?*", (route) => route.fulfill({ json: [] }))
  await page.goto("/")
  await expect(page.getByText("Channels")).toBeVisible()
  await page.getByRole("link", { name: "Channels" }).click()
  await expect(page).toHaveURL(/channels/)
  await expect(page.getByText("demo")).toBeVisible()
})
