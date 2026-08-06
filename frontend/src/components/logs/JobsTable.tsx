import { useMutation, useQueryClient } from "@tanstack/react-query"
import type { ColumnDef } from "@tanstack/react-table"
import { Pencil, Trash2 } from "lucide-react"
import { useState } from "react"

import { JobsService, type PostJobRead } from "@/client"
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
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"
import EditJobDialog from "./EditJobDialog"

const STATUS_STYLES: Record<string, string> = {
  posted: "bg-green-600/15 text-green-600 border-transparent",
  pending: "bg-blue-600/15 text-blue-600 border-transparent",
  processing: "bg-yellow-600/15 text-yellow-600 border-transparent",
  failed: "bg-red-600/15 text-red-600 border-transparent",
  skipped: "bg-zinc-600/15 text-zinc-500 border-transparent",
  deleted: "bg-zinc-600/15 text-zinc-500 border-transparent",
}

function StatusBadge({ status }: { status: string }) {
  return <Badge className={STATUS_STYLES[status] ?? undefined}>{status}</Badge>
}

interface JobActionsProps {
  job: PostJobRead
}

function JobActions({ job }: JobActionsProps) {
  const [editOpen, setEditOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const deleteMutation = useMutation({
    mutationFn: (id: number) => JobsService.deleteJob({ jobId: id }),
    onSuccess: () => {
      showSuccessToast("Post deleted")
      setDeleteOpen(false)
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] })
    },
  })

  return (
    <div className="flex items-center justify-end gap-2">
      <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
        <Pencil className="size-4" />
        Edit
      </Button>
      <Button variant="outline" size="sm" onClick={() => setDeleteOpen(true)}>
        <Trash2 className="size-4" />
        Delete
      </Button>
      <EditJobDialog
        job={editOpen ? job : null}
        onClose={() => setEditOpen(false)}
      />
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete Post</DialogTitle>
            <DialogDescription>
              Delete "{job.title}"? If already posted, the Facebook post is
              removed in the background.
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
              onClick={() => deleteMutation.mutate(job.id)}
            >
              Delete
            </LoadingButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export const jobColumns: ColumnDef<PostJobRead>[] = [
  {
    accessorKey: "title",
    header: "Title",
    cell: ({ row }) => (
      <span className="font-medium line-clamp-2 max-w-64">
        {row.original.title}
      </span>
    ),
  },
  {
    accessorKey: "channel",
    header: "Channel",
    cell: ({ row }) =>
      row.original.channel ? `@${row.original.channel}` : "—",
  },
  {
    accessorKey: "page",
    header: "Page",
    cell: ({ row }) => row.original.page ?? "—",
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge status={row.original.status} />,
  },
  {
    accessorKey: "posted_at",
    header: "Posted At",
    cell: ({ row }) => {
      const v = row.original.posted_at
      return v ? new Date(v).toLocaleString() : "—"
    },
  },
  {
    accessorKey: "scheduled_at",
    header: "Scheduled",
    cell: ({ row }) => {
      const v = row.original.scheduled_at
      return v ? new Date(v).toLocaleString() : "—"
    },
  },
  {
    accessorKey: "error_message",
    header: "Error",
    cell: ({ row }) => (
      <span className="max-w-48 text-xs text-destructive line-clamp-2">
        {row.original.error_message ?? ""}
      </span>
    ),
  },
  {
    id: "actions",
    header: "",
    cell: ({ row }) => <JobActions job={row.original} />,
  },
]

export default jobColumns
