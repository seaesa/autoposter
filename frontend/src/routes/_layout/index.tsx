import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { CircleAlert, Clock3, Send, Share2 } from "lucide-react"

import { JobsService, SchedulerService, StatsService } from "@/client"
import StatsCards from "@/components/dashboard/StatsCards"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { LoadingButton } from "@/components/ui/loading-button"
import { Skeleton } from "@/components/ui/skeleton"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

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
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const queryClient = useQueryClient()
  const today = new Date().toISOString().slice(0, 10)

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["stats"],
    queryFn: () => StatsService.getStats(),
  })

  const { data: failedJobs, isLoading: failedLoading } = useQuery({
    queryKey: ["failedJobs", today],
    queryFn: () => JobsService.listJobs({ status: "failed", date: today }),
  })

  const runNowMutation = useMutation({
    mutationFn: () => SchedulerService.runNow(),
    onSuccess: () => {
      showSuccessToast("Polling started")
      queryClient.invalidateQueries({ queryKey: ["jobs"] })
    },
    onError: handleError.bind(showErrorToast),
  })

  const statsData = (stats ?? {}) as Record<string, unknown>
  const recentFailed = (failedJobs ?? []).slice(0, 5)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          <p className="text-muted-foreground">
            TikTok to Facebook Auto Poster overview
          </p>
        </div>
        <LoadingButton
          loading={runNowMutation.isPending}
          onClick={() => runNowMutation.mutate()}
        >
          Check Now
        </LoadingButton>
      </div>

      {statsLoading ? (
        <Skeleton className="h-28 w-full" />
      ) : (
        <StatsCards
          stats={[
            {
              label: "Posted Today",
              value: Number(statsData.today_posted ?? 0),
              icon: <Send className="size-4" />,
            },
            {
              label: "Pending",
              value: Number(statsData.today_pending ?? 0),
              icon: <Clock3 className="size-4" />,
            },
            {
              label: "Failed Today",
              value: (failedJobs ?? []).length,
              icon: <CircleAlert className="size-4" />,
            },
            {
              label: "Channels",
              value: Number(statsData.channels ?? 0),
              icon: <Share2 className="size-4" />,
            },
          ]}
        />
      )}

      <Card>
        <CardHeader>
          <CardTitle>Recent Failed Posts</CardTitle>
        </CardHeader>
        <CardContent>
          {failedLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : recentFailed.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No failures today. Great job!
            </p>
          ) : (
            <ul className="divide-y">
              {recentFailed.map((job) => (
                <li key={job.id} className="flex items-center gap-3 py-3">
                  <CircleAlert className="size-4 shrink-0 text-destructive" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{job.title}</p>
                    <p className="truncate text-xs text-destructive">
                      {job.error_message ?? "Unknown error"}
                    </p>
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {job.channel ? `@${job.channel}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export default Dashboard
