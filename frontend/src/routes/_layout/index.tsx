import { createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [
      {
        title: "Dashboard - Auto Poster",
      },
    ],
  }),
})

function Dashboard() {
  return (
    <div>
      <h1 className="text-2xl truncate max-w-sm">
        TikTok to Facebook Auto Poster
      </h1>
      <p className="text-muted-foreground">
        Monitor and publish TikTok videos to your Facebook pages.
      </p>
    </div>
  )
}
