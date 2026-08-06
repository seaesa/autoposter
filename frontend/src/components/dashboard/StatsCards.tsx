import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

export interface StatData {
  label: string
  value: number | undefined
  icon: React.ReactNode
  accent?: string
}

const StatsCards = ({ stats }: { stats: StatData[] }) => {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {stats.map((s) => (
        <Card key={s.label}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {s.label}
            </CardTitle>
            <div className={cn("text-muted-foreground", s.accent)}>
              {s.icon}
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{s.value}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

export default StatsCards
