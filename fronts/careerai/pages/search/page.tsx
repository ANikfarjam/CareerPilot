"use client"

import { useCallback, useEffect, useState } from "react"

import { OverviewTab } from "@/components/search/overview-tab"
import { ResultsTab } from "@/components/search/results-tab"
import { SearchTab } from "@/components/search/search-tab"
import { errorMessage } from "@/components/search/format"
import { StatusPill } from "@/components/status-pill"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  ApiError,
  getRun,
  listPortals,
  listRuns,
  listTargetPositions,
  startRun,
  type AgentRun,
  type ManualPosition,
} from "@/lib/api"

const POLL_MS = 2000

type Tab = "overview" | "search" | "results"

export default function SearchPage() {
  const [tab, setTab] = useState<Tab>("overview")
  const [portals, setPortals] = useState<string[]>([])
  const [positions, setPositions] = useState<string[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [manualQueue, setManualQueue] = useState<ManualPosition[]>([])
  const [run, setRun] = useState<AgentRun | null>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [total, setTotal] = useState<number | null>(null)

  const isRunning = starting || run?.status === "queued" || run?.status === "running"

  // Portals to search, target positions, and the latest run (it may still be going).
  useEffect(() => {
    listPortals()
      .then((names) => {
        setPortals(names)
        setSelected(names)
      })
      .catch((e) => setError(errorMessage(e)))
    listTargetPositions()
      .then(setPositions)
      .catch((e) => setError(errorMessage(e)))
    listRuns()
      .then((runs) => setRun(runs[0] ?? null))
      .catch(() => {})
  }, [])

  // Poll the run until it finishes; its logs fill the pipeline as it goes.
  const runId = run?.id
  const runActive = run?.status === "queued" || run?.status === "running"
  useEffect(() => {
    if (!runId || !runActive) return
    let stopped = false
    const timer = setInterval(async () => {
      try {
        const next = await getRun(runId)
        if (!stopped) setRun(next)
      } catch (e) {
        if (stopped) return
        if (e instanceof ApiError && e.status === 404) setRun(null) // the API restarted; runs live in its memory
        else setError(errorMessage(e))
      }
    }, POLL_MS)
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [runId, runActive])

  // Portals added on the Overview tab are searched by default; removed ones are deselected.
  const changePortals = (names: string[]) => {
    setSelected((current) => [...current.filter((n) => names.includes(n)), ...names.filter((n) => !portals.includes(n))])
    setPortals(names)
  }

  const handleRun = async () => {
    setStarting(true)
    setError(null)
    try {
      setRun(await startRun({ portals: selected, manual_positions: manualQueue }))
      setManualQueue([]) // they are part of this run now
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 409
          ? "Another agent run is in progress. Try again when it finishes."
          : errorMessage(e),
      )
    } finally {
      setStarting(false)
    }
  }

  const onTotal = useCallback((n: number) => setTotal(n), [])
  // Reload the results once a run has saved its jobs.
  const refreshKey = run?.status === "succeeded" ? `${run.id}` : ""

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-4 py-8 sm:px-6 sm:py-10">
      <header className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Job search</h1>
          <p className="text-sm text-muted-foreground">
            Search your portals for target positions, score each posting against your profile and save the matches.
          </p>
        </div>
        <StatusPill running={isRunning} />
      </header>

      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)} className="gap-6">
        <TabsList variant="line" className="w-full justify-start border-b">
          <TabsTrigger value="overview" className="flex-none px-3">
            Overview
          </TabsTrigger>
          <TabsTrigger value="search" className="flex-none px-3">
            Search
          </TabsTrigger>
          <TabsTrigger value="results" className="flex-none px-3">
            Results
            {total !== null && (
              <span className="rounded-md bg-muted px-1.5 text-xs font-medium tabular-nums text-muted-foreground">{total}</span>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab
            portals={portals}
            positions={positions}
            onPortalsChange={changePortals}
            onPositionsChange={setPositions}
            locked={isRunning}
          />
        </TabsContent>
        <TabsContent value="search">
          <SearchTab
            portals={portals}
            selected={selected}
            onSelectedChange={setSelected}
            manualQueue={manualQueue}
            onManualQueueChange={setManualQueue}
            run={run}
            isRunning={isRunning}
            error={error}
            onRun={handleRun}
            onViewResults={() => setTab("results")}
          />
        </TabsContent>
        <TabsContent value="results" keepMounted>
          <ResultsTab refreshKey={refreshKey} onTotal={onTotal} />
        </TabsContent>
      </Tabs>
    </main>
  )
}
