import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import type { ColumnDef } from "@tanstack/react-table"
import { Link2, Trash2 } from "lucide-react"
import { useState } from "react"

import { type TikTokChannelRead, TiktokChannelsService } from "@/client"
import AddChannelDialog from "@/components/Channels/AddChannelDialog"
import MappingDialog from "@/components/Channels/MappingDialog"
import { DataTable } from "@/components/Common/DataTable"
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
  const { data: channels, isLoading } = useQuery({
    queryKey: ["channels"],
    queryFn: () => TiktokChannelsService.listChannels(),
  })

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">TikTok Channels</h1>
        <AddChannelDialog />
      </div>
      {isLoading ? (
        <Skeleton className="mt-4 h-64 w-full" />
      ) : (
        <DataTable
          columns={columns}
          data={(channels ?? []) as TikTokChannelRead[]}
        />
      )}
    </div>
  )
}

function ChannelActions({ channel }: { channel: TikTokChannelRead }) {
  const [mappingOpen, setMappingOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const deleteMutation = useMutation({
    mutationFn: (id: number) =>
      TiktokChannelsService.deleteChannel({ channelId: id }),
    onSuccess: () => {
      showSuccessToast("Channel deleted")
      setDeleteOpen(false)
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["channels"] })
    },
  })

  return (
    <div className="flex items-center justify-end gap-2">
      <Button variant="outline" size="sm" onClick={() => setMappingOpen(true)}>
        <Link2 className="size-4" />
        Pages
      </Button>
      <Button variant="outline" size="sm" onClick={() => setDeleteOpen(true)}>
        <Trash2 className="size-4" />
        Delete
      </Button>
      <MappingDialog
        channel={channel}
        isOpen={mappingOpen}
        onOpenChange={setMappingOpen}
      />
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete Channel</DialogTitle>
            <DialogDescription>
              Delete @{channel.username}? This cannot be undone.
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
                if (channel.id !== undefined) {
                  deleteMutation.mutate(channel.id)
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

const columns: ColumnDef<TikTokChannelRead>[] = [
  {
    accessorKey: "username",
    header: "Username",
    cell: ({ row }) => (
      <span className="font-medium">@{row.original.username}</span>
    ),
  },
  {
    accessorKey: "display_name",
    header: "Display Name",
    cell: ({ row }) => row.original.display_name ?? "—",
  },
  {
    id: "pages",
    header: "Mapped Pages",
    cell: ({ row }) => {
      const pages = row.original.pages ?? []
      if (pages.length === 0) {
        return <span className="text-sm text-muted-foreground">None</span>
      }
      return (
        <div className="flex flex-wrap gap-1">
          {pages.map((p) => (
            <Badge key={(p as { id?: number }).id} variant="secondary">
              {(p as { name?: string }).name}
            </Badge>
          ))}
        </div>
      )
    },
  },
  {
    accessorKey: "backfill_remaining",
    header: "Backfill",
    cell: ({ row }) => row.original.backfill_remaining || "—",
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
    accessorKey: "last_checked_at",
    header: "Last Checked",
    cell: ({ row }) => {
      const v = row.original.last_checked_at
      return v ? new Date(v).toLocaleString() : "Never"
    },
  },
  {
    id: "actions",
    header: "",
    cell: ({ row }) => <ChannelActions channel={row.original} />,
  },
]

export default Channels
