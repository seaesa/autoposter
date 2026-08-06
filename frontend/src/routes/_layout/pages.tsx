import { createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/pages")({
  component: Pages,
  head: () => ({
    meta: [
      {
        title: "Pages - Auto Poster",
      },
    ],
  }),
})

function Pages() {
  return <div>Pages</div>
}
