"use client"

import { useEffect, useRef } from "react"
import { Check, Database, Gauge, Globe, LoaderCircle, X, type LucideIcon } from "lucide-react"

import type { AgentRun, RunLog } from "@/lib/api"
import { cn } from "@/lib/utils"

import { formatTime } from "./format"

type Stage = RunLog["stage"]
type StageState = "pending" | "running" | "done" | "error" | "skipped"

// The graph's three nodes, in order (agents/graph/graph.py).
const STAGES: { id: Stage; label: string; icon: LucideIcon }[] = [
  { id: "portal_search", label: "Search", icon: Globe },
  { id: "qualification_check", label: "Qualify", icon: Gauge },
  { id: "db_ingestion", label: "Ingest", icon: Database },
]

// Each stage's state from the run's status and current stage. A succeeded run whose graph
// ended before a stage (no positions found) marks that stage skipped.
function stageStates(run: AgentRun | null): StageState[] {
  if (!run) return STAGES.map(() => "pending")
  const current = Math.max(0, STAGES.findIndex((s) => s.id === run.stage))
  return STAGES.map((_, i) => {
    if (i < current) return "done"
    if (i > current) return run.status === "succeeded" ? "skipped" : "pending"
    if (run.status === "succeeded") return "done"
    if (run.status === "failed") return "error"
    return "running"
  })
}

// What each stage did, once the run finished.
function stageCounts(run: AgentRun | null): (string | null)[] {
  const s = run?.summary
  if (!s) return [null, null, null]
  return [`${s.positions} found`, `${s.scored} scored`, `${s.ingested} saved`]
}

function stageErrors(run: AgentRun | null): number[] {
  const s = run?.summary
  if (!s) return [0, 0, 0]
  return [s.portal_errors.length, s.qualification_errors.length, s.ingestion_errors.length]
}

// Search tab's run view: the three stages as connected icons, then each stage's live log.
export function Pipeline({ run }: { run: AgentRun | null }) {
  const states = stageStates(run)
  const counts = stageCounts(run)
  const errors = stageErrors(run)

  return (
    <div className="space-y-6">
      <ol className="grid grid-cols-3 rounded-xl border bg-card px-2 py-8 sm:px-6">
        {STAGES.map((stage, i) => (
          <li key={stage.id} className="relative flex flex-col items-center gap-3 text-center">
            {i < STAGES.length - 1 && (
              <span
                aria-hidden
                className="absolute top-7 left-[calc(50%+2.25rem)] h-0.5 w-[calc(100%-4.5rem)] overflow-hidden rounded-full bg-border"
              >
                <span
                  className={cn(
                    "block h-full bg-brand-green transition-[width] duration-700",
                    states[i] === "done" && states[i + 1] !== "skipped" ? "w-full" : "w-0",
                  )}
                />
              </span>
            )}
            <StageIcon icon={stage.icon} state={states[i]} />
            <div className="space-y-0.5">
              <p className="text-sm font-medium">{stage.label}</p>
              <p className="text-xs text-muted-foreground">{stageCaption(states[i], counts[i])}</p>
            </div>
          </li>
        ))}
      </ol>

      <div className="grid gap-4 md:grid-cols-3">
        {STAGES.map((stage, i) => (
          <StageLog
            key={stage.id}
            label={stage.label}
            state={states[i]}
            errors={errors[i]}
            logs={run?.logs.filter((l) => l.stage === stage.id) ?? []}
          />
        ))}
      </div>
    </div>
  )
}

function stageCaption(state: StageState, count: string | null) {
  switch (state) {
    case "running":
      return "In progress"
    case "done":
      return count ?? "Done"
    case "error":
      return "Failed"
    case "skipped":
      return "Skipped"
    default:
      return "Waiting"
  }
}

function StageIcon({ icon: Icon, state }: { icon: LucideIcon; state: StageState }) {
  return (
    <div className="relative">
      <div
        className={cn(
          "flex size-14 items-center justify-center rounded-full border-2 bg-background transition-colors",
          state === "pending" && "border-border text-muted-foreground/60",
          state === "skipped" && "border-dashed border-border text-muted-foreground/40",
          state === "running" && "border-brand-teal text-brand-teal",
          state === "done" && "border-brand-green text-brand-green",
          state === "error" && "border-destructive text-destructive",
        )}
      >
        <Icon className="size-6" />
      </div>
      {state === "running" && (
        <span className="absolute -inset-1 animate-pulse rounded-full ring-4 ring-brand-teal/15" aria-hidden />
      )}
      {(state === "running" || state === "done" || state === "error") && (
        <span
          className={cn(
            "absolute -right-0.5 -bottom-0.5 flex size-5 items-center justify-center rounded-full border-2 border-card text-background",
            state === "running" && "bg-brand-teal",
            state === "done" && "bg-brand-green",
            state === "error" && "bg-destructive",
          )}
        >
          {state === "running" && <LoaderCircle className="size-3 animate-spin" />}
          {state === "done" && <Check className="size-3" strokeWidth={3} />}
          {state === "error" && <X className="size-3" strokeWidth={3} />}
        </span>
      )}
    </div>
  )
}

function StageLog({ label, state, errors, logs }: { label: string; state: StageState; errors: number; logs: RunLog[] }) {
  const box = useRef<HTMLDivElement>(null)

  // Follow the newest line (scrolls the log box only, not the page).
  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight
  }, [logs.length])

  return (
    <section className="flex flex-col overflow-hidden rounded-xl border bg-card">
      <header className="flex items-center justify-between border-b px-4 py-2.5">
        <h3 className="text-sm font-medium">{label} log</h3>
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          {errors > 0 && <span className="text-destructive">{errors} error{errors === 1 ? "" : "s"}</span>}
          <span className="tabular-nums">{logs.length}</span>
        </span>
      </header>
      <div ref={box} className="h-72 overflow-y-auto px-4 py-3 font-mono text-xs leading-relaxed">
        {logs.length === 0 ? (
          <p className="text-muted-foreground">
            {state === "skipped" ? "Skipped: nothing to process." : state === "running" ? "Starting…" : "No activity yet."}
          </p>
        ) : (
          <ul className="space-y-1">
            {logs.map((log, i) => (
              <li key={i} className="flex gap-2">
                <span className="shrink-0 text-muted-foreground/70 tabular-nums">{formatTime(log.at)}</span>
                <span
                  className={cn(
                    "min-w-0 break-words",
                    log.level === "success" && "text-brand-green",
                    log.level === "error" && "text-destructive",
                  )}
                >
                  {log.message}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
