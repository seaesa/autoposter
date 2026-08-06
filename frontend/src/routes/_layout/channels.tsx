import { createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/channels")({
  component: Channels,
  head: () => ({
    meta: [
      {
        title: "Channels - Auto Poster",
      },
    ],
  }),
})

function Channels() {
  return <div>Channels</div>
}
