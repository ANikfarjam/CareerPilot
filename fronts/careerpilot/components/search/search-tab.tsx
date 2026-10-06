"use client"

import { ChevronDown, LoaderCircle, Search, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import type { AgentRun, ManualPosition } from "@/lib/api"

import { AddPositionDrawer } from "./add-position-drawer"
import { Pipeline } from "./pipeline"

type Props = {
  portals: string[]
  selected: string[]
  onSelectedChange: (names: string[]) => void
  manualQueue: ManualPosition[]
  onManualQueueChange: (queue: ManualPosition[]) => void
  run: AgentRun | null
  isRunning: boolean
  error: string | null
  onRun: () => void
  onViewResults: () => void
}

// Search tab: what to search (portals + manual positions), the run button and the live pipeline.
export function SearchTab({
  portals,
  selected,
  onSelectedChange,
  manualQueue,
  onManualQueueChange,
  run,
  isRunning,
  error,
  onRun,
  onViewResults,
}: Props) {
  const toggle = (name: string, on: boolean) =>
    onSelectedChange(on ? [...selected, name] : selected.filter((n) => n !== name))

  return (
    <div className="space-y-6">
      <Collapsible className="rounded-xl border bg-card">
        <div className="flex flex-wrap items-center gap-2 p-3">
          <CollapsibleTrigger
            render={<Button variant="ghost" className="group" />}
            disabled={isRunning}
          >
            Portals
            <span className="text-muted-foreground tabular-nums">
              {selected.length} of {portals.length}
            </span>
            <ChevronDown className="transition-transform group-data-panel-open:rotate-180" />
          </CollapsibleTrigger>
          <AddPositionDrawer disabled={isRunning} onAdd={(p) => onManualQueueChange([...manualQueue, p])} />
          <Button
            onClick={onRun}
            disabled={isRunning || (selected.length === 0 && manualQueue.length === 0)}
            className="ml-auto"
          >
            {isRunning ? <LoaderCircle className="animate-spin" /> : <Search />}
            {isRunning ? "Searching…" : "Run search"}
          </Button>
        </div>

        <CollapsibleContent className="border-t p-4">
          <div className="mb-3 flex gap-3 text-xs">
            <button type="button" className="text-muted-foreground hover:text-foreground" onClick={() => onSelectedChange(portals)}>
              Select all
            </button>
            <button type="button" className="text-muted-foreground hover:text-foreground" onClick={() => onSelectedChange([])}>
              Clear
            </button>
          </div>
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {portals.map((name) => (
              <li key={name}>
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <Checkbox checked={selected.includes(name)} onCheckedChange={(on) => toggle(name, on)} />
                  <span className="truncate">{name}</span>
                </label>
              </li>
            ))}
          </ul>
        </CollapsibleContent>

        {manualQueue.length > 0 && (
          <div className="border-t px-4 py-3">
            <p className="mb-2 text-xs text-muted-foreground">Manual positions, scored and saved on the next run</p>
            <ul className="flex flex-wrap gap-2">
              {manualQueue.map((p, i) => (
                <li key={p.link} className="inline-flex items-center gap-1 rounded-md border py-1 pr-1 pl-2.5 text-sm">
                  {p.position} <span className="text-muted-foreground">· {p.company}</span>
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    aria-label={`Remove ${p.position}`}
                    disabled={isRunning}
                    onClick={() => onManualQueueChange(manualQueue.filter((_, j) => j !== i))}
                  >
                    <X />
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Collapsible>

      {error && <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">{error}</p>}
      {run?.status === "failed" && (
        <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          Run failed: {run.error ?? "unknown error"}
        </p>
      )}

      <Pipeline run={run} />

      {run?.status === "succeeded" && (
        <div className="flex items-center justify-between rounded-xl border bg-card px-4 py-3 text-sm">
          <span className="text-muted-foreground">
            Run finished · {run.summary?.ingested ?? 0} jobs saved
            {run.summary?.skipped_known ? ` · ${run.summary.skipped_known} already saved` : ""}
          </span>
          <Button variant="link" onClick={onViewResults} className="px-0">
            View results →
          </Button>
        </div>
      )}
    </div>
  )
}
