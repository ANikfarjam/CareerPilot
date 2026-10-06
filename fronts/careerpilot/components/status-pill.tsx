import { cn } from "@/lib/utils"

// Pulsing pill that shows whether an agent run is in progress (search and analytics pages).
export function StatusPill({ running, label }: { running: boolean; label?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium",
        running ? "border-brand-green/30 bg-brand-green/10 text-brand-green" : "text-muted-foreground",
      )}
    >
      <span className="relative flex size-2">
        {running && (
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-brand-green opacity-75" />
        )}
        <span className={cn("relative inline-flex size-2 rounded-full", running ? "bg-brand-green" : "bg-muted-foreground/50")} />
      </span>
      {label ?? (running ? "Agents running" : "Idle")}
    </span>
  )
}
