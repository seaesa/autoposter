export function Footer() {
  const currentYear = new Date().getFullYear()

  return (
    <footer className="border-t py-4 px-6">
      <div className="flex items-center justify-between gap-4">
        <p className="text-muted-foreground text-sm">
          TikTok to Facebook Auto Poster - {currentYear}
        </p>
      </div>
    </footer>
  )
}
