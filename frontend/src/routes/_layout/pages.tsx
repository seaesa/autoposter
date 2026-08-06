import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import type { ColumnDef } from "@tanstack/react-table"
import { Trash2 } from "lucide-react"
import { useState } from "react"

import { type FacebookPageRead, FacebookPagesService } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import AddPageDialog from "@/components/Pages/AddPageDialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { LoadingButton } from "@/components/ui/loading-button"
import { Skeleton } from "@/components/ui/skeleton"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

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
  const { data: pages, isLoading } = useQuery({
    queryKey: ["pages"],
    queryFn: () => FacebookPagesService.listPages(),
  })

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Facebook Pages</h1>
        <AddPageDialog />
      </div>
      {isLoading ? (
        <Skeleton className="mt-4 h-64 w-full" />
      ) : (
        <DataTable
          columns={columns}
          data={(pages ?? []) as FacebookPageRead[]}
        />
      )}
    </div>
  )
}

function PageActions({ page }: { page: FacebookPageRead }) {
  const [deleteOpen, setDeleteOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const deleteMutation = useMutation({
    mutationFn: (id: number) => FacebookPagesService.deletePage({ pageId: id }),
    onSuccess: () => {
      showSuccessToast("Page deleted")
      setDeleteOpen(false)
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["pages"] })
      queryClient.invalidateQueries({ queryKey: ["channels"] })
    },
  })

  return (
    <div className="flex items-center justify-end">
      <Button variant="outline" size="sm" onClick={() => setDeleteOpen(true)}>
        <Trash2 className="size-4" />
        Delete
      </Button>
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete Page</DialogTitle>
            <DialogDescription>
              Delete {page.name}? Its access token will be removed.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <LoadingButton
              variant="destructive"
              loading={deleteMutation.isPending}
              onClick={() => {
                if (page.id !== undefined) {
                  deleteMutation.mutate(page.id)
                }
              }}
            >
              Delete
            </LoadingButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

const columns: ColumnDef<FacebookPageRead>[] = [
  {
    accessorKey: "name",
    header: "Name",
    cell: ({ row }) => <span className="font-medium">{row.original.name}</span>,
  },
  {
    accessorKey: "page_id",
    header: "Page ID",
    cell: ({ row }) => (
      <span className="text-muted-foreground">{row.original.page_id}</span>
    ),
  },
  {
    accessorKey: "max_posts_per_day",
    header: "Max / Day",
    cell: ({ row }) => row.original.max_posts_per_day,
  },
  {
    accessorKey: "min_interval_minutes",
    header: "Min Interval",
    cell: ({ row }) => `${row.original.min_interval_minutes} min`,
  },
  {
    id: "channels",
    header: "Feeding Channels",
    cell: ({ row }) => {
      const channels = row.original.channels ?? []
      if (channels.length === 0) {
        return <span className="text-sm text-muted-foreground">None</span>
      }
      return (
        <div className="flex flex-wrap gap-1">
          {channels.map((c) => (
            <Badge key={(c as { id?: number }).id} variant="secondary">
              @{(c as { username?: string }).username}
            </Badge>
          ))}
        </div>
      )
    },
  },
  {
    accessorKey: "is_active",
    header: "Status",
    cell: ({ row }) =>
      row.original.is_active ? (
        <Badge>Active</Badge>
      ) : (
        <Badge variant="outline">Inactive</Badge>
      ),
  },
  {
    id: "actions",
    header: "",
    cell: ({ row }) => <PageActions page={row.original} />,
  },
]

export default Pages
