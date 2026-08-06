import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useState } from "react"

import {
  FacebookPagesService,
  JobsService,
  type PostJobRead,
  TiktokChannelsService,
} from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import { jobColumns } from "@/components/logs/JobsTable"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"

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

const STATUSES = [
  "pending",
  "processing",
  "posted",
  "failed",
  "skipped",
  "deleted",
]

function Logs() {
  const today = new Date().toISOString().slice(0, 10)
  const [date, setDate] = useState(today)
  const [channelId, setChannelId] = useState("")
  const [pageId, setPageId] = useState("")
  const [status, setStatus] = useState("")

  const {
    data: jobs,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["jobs", date, channelId, pageId, status],
    queryFn: () =>
      JobsService.listJobs({
        date,
        channelId: channelId ? Number(channelId) : undefined,
        pageId: pageId ? Number(pageId) : undefined,
        status: status || undefined,
      }),
  })

  const { data: channels } = useQuery({
    queryKey: ["channels"],
    queryFn: () => TiktokChannelsService.listChannels(),
  })

  const { data: pages } = useQuery({
    queryKey: ["pages"],
    queryFn: () => FacebookPagesService.listPages(),
  })

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold">Post Logs</h1>
        <div className="flex flex-wrap items-center gap-2">
          <Input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="w-44"
          />
          <Select value={channelId} onValueChange={setChannelId}>
            <SelectTrigger className="w-44">
              <SelectValue placeholder="All channels" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All channels</SelectItem>
              {(channels ?? []).map((c) => (
                <SelectItem key={c.id} value={String(c.id)}>
                  @{c.username}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={pageId} onValueChange={setPageId}>
            <SelectTrigger className="w-44">
              <SelectValue placeholder="All pages" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All pages</SelectItem>
              {(pages ?? []).map((p) => (
                <SelectItem key={p.id} value={String(p.id)}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="w-44">
              <SelectValue placeholder="All statuses" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              {STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={() => refetch()}>
            Refresh
          </Button>
        </div>
      </div>
      <div className="mt-4">
        {isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          <DataTable
            columns={jobColumns}
            data={(jobs ?? []) as PostJobRead[]}
          />
        )}
      </div>
    </div>
  )
}

export default Logs
