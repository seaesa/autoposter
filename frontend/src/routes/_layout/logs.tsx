import { createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/logs")({
  component: Logs,
  head: () => ({
    meta: [
      {
        title: "Logs - Auto Poster",
      },
    ],
  }),
})

function Logs() {
  return <div>Logs</div>
}
