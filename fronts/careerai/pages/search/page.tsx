"use client"

import { useEffect, useState } from "react"
import {
  Bot,
  Briefcase,
  Building2,
  Circle,
  CircleCheck,
  CircleX,
  ExternalLink,
  Gauge,
  Globe,
  LoaderCircle,
  MapPin,
  Search,
  Sparkles,
} from "lucide-react"

import { StatTile } from "@/components/stat-tile"
import { StatusPill } from "@/components/status-pill"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  ApiError,
  getRun,
  listJobs,
  listPortals,
  listRuns,
  listTargetPositions,
  startRun,
  type AgentRun,
  type Job,
} from "@/lib/api"
import { cn } from "@/lib/utils"

type StepStatus = "pending" | "running" | "done" | "error"

type AgentStep = {
  id: string
  agent: string
  message: string
  status: StepStatus
}

const POLL_MS = 3000

export default function SearchPage() {
  const [portals, setPortals] = useState<string[]>([])
  const [positions, setPositions] = useState<string[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [run, setRun] = useState<AgentRun | null>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [results, setResults] = useState<Job[]>([])
  const [total, setTotal] = useState(0)

  const isRunning = starting || run?.status === "queued" || run?.status === "running"
  const agentSteps = run ? runSteps(run) : []

  const loadJobs = () =>
    listJobs({ sort_by: "update_at", order: "desc", limit: 50 })
      .then((page) => {
        setResults(page.items)
        setTotal(page.total)
      })
      .catch((e) => setError(errorMessage(e)))

  // Portals to search, target positions, saved jobs, and the latest run (it may still be going).
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
    loadJobs()
    listRuns()
      .then((runs) => setRun(runs[0] ?? null))
      .catch(() => {})
  }, [])

  // Poll the run until it finishes, then reload the saved jobs.
  const runId = run?.id
  const runActive = run?.status === "queued" || run?.status === "running"
  useEffect(() => {
    if (!runId || !runActive) return
    let stopped = false
    const timer = setInterval(async () => {
      try {
        const next = await getRun(runId)
        if (stopped) return
        setRun(next)
        if (next.status === "succeeded") loadJobs()
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

  const handleOnClick = async () => {
    setStarting(true)
    setError(null)
    try {
      setRun(await startRun({ portals: selected }))
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

  const togglePortal = (name: string) =>
    setSelected((names) => (names.includes(name) ? names.filter((n) => n !== name) : [...names, name]))

  const avgMatch = results.length
    ? Math.round((results.reduce((sum, r) => sum + r.compatibility, 0) / results.length) * 10)
    : null

  return (
    <div className="relative flex min-h-full flex-1 flex-col">
      {/* Brand glow */}
      <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[480px] bg-[radial-gradient(60%_60%_at_20%_0%,color-mix(in_oklch,var(--brand-blue)_30%,transparent),transparent),radial-gradient(50%_50%_at_85%_10%,color-mix(in_oklch,var(--brand-green)_18%,transparent),transparent)]" />

      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-4 py-8 sm:px-6 sm:py-10">
        <div className="flex justify-end">
          <StatusPill running={isRunning} />
        </div>

        {/* Hero + target roles */}
        <section className="rounded-2xl border bg-card/60 p-6 shadow-xl shadow-black/20 backdrop-blur sm:p-8">
          <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
            <div className="space-y-3">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-teal/30 bg-brand-teal/10 px-3 py-1 text-xs font-medium text-brand-teal">
                <Sparkles className="size-3.5" />
                AI job search
              </span>
              <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
                Find roles that{" "}
                <span className="bg-linear-to-r from-brand-teal to-brand-green bg-clip-text text-transparent">
                  fit you
                </span>
              </h1>
              <p className="max-w-xl text-sm leading-relaxed text-muted-foreground sm:text-base">
                Agents search job boards for your target roles and score every
                posting against your profile.
              </p>
            </div>
            <Button
              size="lg"
              onClick={handleOnClick}
              disabled={isRunning || selected.length === 0}
              className="h-12 rounded-xl bg-linear-to-r from-brand-blue via-brand-teal to-brand-green px-6 text-base font-semibold text-brand-navy shadow-lg shadow-brand-teal/25 transition hover:shadow-brand-teal/40 hover:brightness-110"
            >
              {isRunning ? <LoaderCircle className="size-5 animate-spin" /> : <Search className="size-5" />}
              {isRunning ? "Searching…" : "Run search"}
            </Button>
          </div>

          {error && <p className="mt-4 text-sm text-destructive">{error}</p>}

          <div className="mt-8 border-t pt-6">
            <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Portals to search
            </h2>
            {portals.length === 0 ? (
              <p className="text-sm text-muted-foreground">No enabled portals in portals.yml.</p>
            ) : (
              <ul className="flex flex-wrap gap-2">
                {portals.map((name) => (
                  <li key={name}>
                    <button
                      type="button"
                      onClick={() => togglePortal(name)}
                      disabled={isRunning}
                      aria-pressed={selected.includes(name)}
                      className={cn(
                        "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition",
                        selected.includes(name)
                          ? "border-brand-blue/30 bg-brand-blue/10"
                          : "text-muted-foreground opacity-60 hover:opacity-100",
                      )}
                    >
                      <Globe className="size-3.5 text-brand-teal" />
                      {name}
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <h2 className="mt-6 mb-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Target positions
            </h2>
            {positions.length === 0 ? (
              <p className="text-sm text-muted-foreground">No positive title keywords in portals.yml.</p>
            ) : (
              <ul className="flex flex-wrap gap-2">
                {positions.map((name) => (
                  <li
                    key={name}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-brand-green/30 bg-brand-green/10 px-3 py-1.5 text-sm font-medium"
                  >
                    <Briefcase className="size-3.5 text-brand-green" />
                    {titleCase(name)}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        {/* Stats */}
        <section className="grid gap-4 sm:grid-cols-3">
          <StatTile icon={Globe} label="Portals" value={`${selected.length}/${portals.length}`} />
          <StatTile icon={Briefcase} label="Postings saved" value={total} />
          <StatTile icon={Gauge} label="Avg. match" value={avgMatch === null ? "—" : `${avgMatch}%`} />
        </section>

        <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
          {/* Agent activity */}
          <section className="h-fit rounded-2xl border bg-card p-5">
            <h2 className="mb-5 flex items-center gap-2 font-medium">
              <Bot className="size-4 text-brand-teal" />
              Agent activity
            </h2>

            {agentSteps.length === 0 ? (
              <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed py-10 text-center">
                {isRunning ? (
                  <LoaderCircle className="size-6 animate-spin text-brand-teal" />
                ) : (
                  <Bot className="size-6 text-muted-foreground" />
                )}
                <p className="max-w-52 text-sm text-muted-foreground">
                  {isRunning ? "Starting agents…" : "Run a search to watch the agents work."}
                </p>
              </div>
            ) : (
              <ol className="relative space-y-5 before:absolute before:top-3 before:bottom-3 before:left-[11px] before:w-px before:bg-border">
                {agentSteps.map((step) => (
                  <li key={step.id} className="relative flex gap-3">
                    <StepIcon status={step.status} />
                    <div className="min-w-0 space-y-0.5 pt-0.5">
                      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                        {step.agent}
                      </p>
                      <p
                        className={cn(
                          "text-sm leading-snug",
                          step.status === "running" && "text-foreground",
                          step.status === "pending" && "text-muted-foreground",
                        )}
                      >
                        {step.message}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>

          {/* Results */}
          <section className="min-w-0 overflow-hidden rounded-2xl border bg-card">
            <div className="flex items-center justify-between px-5 py-4">
              <h2 className="font-medium">Results</h2>
              <span className="rounded-full bg-brand-teal/10 px-2.5 py-0.5 text-xs font-medium text-brand-teal">
                {total} saved
              </span>
            </div>

            {/* One column per job_board_table field (JobOut) */}
            <Table>
              <TableHeader className="bg-muted/50">
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-5 text-xs uppercase tracking-wider text-muted-foreground">Company</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Position</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Job type</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Action</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Compatibility</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Updated</TableHead>
                  <TableHead className="pr-5 text-right text-xs uppercase tracking-wider text-muted-foreground">Link</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {results.map((job) => (
                  <TableRow key={job.id} className="group">
                    <TableCell className="py-4 pl-5">
                      <div className="flex items-center gap-3">
                        <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-linear-to-br from-brand-blue/25 to-brand-green/25 text-sm font-semibold">
                          {job.company_name.charAt(0)}
                        </div>
                        <span className="font-medium">{job.company_name}</span>
                      </div>
                    </TableCell>
                    <TableCell className="max-w-72 whitespace-normal">
                      <p className="font-medium">{job.position}</p>
                      {job.post_id && <p className="text-xs text-muted-foreground">#{job.post_id}</p>}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      <span className="inline-flex items-center gap-1">
                        <MapPin className="size-3.5" />
                        {titleCase(job.job_type)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="rounded-md border bg-muted/50 px-2 py-0.5 text-xs font-medium">
                        {titleCase(job.action)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <MatchScore score={job.compatibility} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">{formatDate(job.update_at)}</TableCell>
                    <TableCell className="pr-5 text-right">
                      {job.link ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          nativeButton={false}
                          render={<a href={job.link} target="_blank" rel="noopener noreferrer" />}
                          className="text-brand-teal opacity-70 group-hover:opacity-100"
                        >
                          View
                          <ExternalLink />
                        </Button>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
              {results.length === 0 && (
                <TableCaption className="mt-0 border-t py-16">
                  {isRunning ? "Waiting for results…" : "No results yet. Run a search to get started."}
                </TableCaption>
              )}
            </Table>
          </section>
        </div>
      </main>
    </div>
  )
}

// The graph's three nodes, from the run's status and, once it finished, its summary.
function runSteps(run: AgentRun): AgentStep[] {
  const nodes = ["Portal search", "Qualification check", "DB ingestion"]
  if (run.status === "queued" || run.status === "running") {
    const message = run.status === "queued" ? "Queued" : `Searching ${run.portals.join(", ")}, scoring and saving positions`
    return nodes.map((agent, i) => ({
      id: agent,
      agent,
      message: i === 0 ? message : "Waiting",
      status: i === 0 ? "running" : "pending",
    }))
  }
  if (run.status === "failed" || !run.summary) {
    return [{ id: "error", agent: "Run failed", message: run.error ?? "Unknown error", status: "error" }]
  }
  const s = run.summary
  const step = (agent: string, message: string, errors: unknown[]): AgentStep => ({
    id: agent,
    agent,
    message: errors.length ? `${message} (${errors.length} errors)` : message,
    status: errors.length ? "error" : "done",
  })
  return [
    step(nodes[0], `Found ${s.positions} positions`, s.portal_errors),
    step(nodes[1], `Scored ${s.scored} positions`, s.qualification_errors),
    step(nodes[2], `Saved ${s.ingested} jobs`, s.ingestion_errors),
  ]
}

function errorMessage(e: unknown) {
  return e instanceof Error ? e.message : String(e)
}

function titleCase(value: string) {
  return value.replace(/[_-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" })
}

function StepIcon({ status }: { status: StepStatus }) {
  const base = "relative z-10 size-6 shrink-0 rounded-full bg-card p-0.5"
  switch (status) {
    case "running":
      return <LoaderCircle className={cn(base, "animate-spin text-brand-teal")} />
    case "done":
      return <CircleCheck className={cn(base, "text-brand-green")} />
    case "error":
      return <CircleX className={cn(base, "text-destructive")} />
    default:
      return <Circle className={cn(base, "text-muted-foreground/40")} />
  }
}

// compatibility is qualification_check's 0-10 score.
function MatchScore({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-linear-to-r from-brand-blue via-brand-teal to-brand-green"
          style={{ width: `${score * 10}%` }}
        />
      </div>
      <span className="text-sm font-medium tabular-nums">{score}/10</span>
    </div>
  )
}
