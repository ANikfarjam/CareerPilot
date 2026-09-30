"use client"

import { useState } from "react"
import {
  Bot,
  Briefcase,
  Building2,
  Circle,
  CircleCheck,
  CircleX,
  ExternalLink,
  Gauge,
  LoaderCircle,
  MapPin,
  Search,
  Sparkles,
} from "lucide-react"

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
import { cn } from "@/lib/utils"

type StepStatus = "pending" | "running" | "done" | "error"

type AgentStep = {
  id: string
  agent: string
  message: string
  status: StepStatus
}

type JobResult = {
  id: string
  title: string
  company: string
  location: string
  source: string
  matchScore: number
  postedAt: string
  url: string
}

export default function SearchPage() {
  const [targetRoles] = useState<string[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [agentSteps] = useState<AgentStep[]>([])
  const [results] = useState<JobResult[]>([])

  // TODO: trigger the search graph and stream agent steps / results into state
  const handleOnClick = () => {
    setIsRunning((running) => !running)
  }

  const avgMatch = results.length
    ? Math.round(results.reduce((sum, r) => sum + r.matchScore, 0) / results.length)
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
              disabled={isRunning}
              className="h-12 rounded-xl bg-linear-to-r from-brand-blue via-brand-teal to-brand-green px-6 text-base font-semibold text-brand-navy shadow-lg shadow-brand-teal/25 transition hover:shadow-brand-teal/40 hover:brightness-110"
            >
              {isRunning ? <LoaderCircle className="size-5 animate-spin" /> : <Search className="size-5" />}
              {isRunning ? "Searching…" : "Run search"}
            </Button>
          </div>

          <div className="mt-8 border-t pt-6">
            <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Target roles
            </h2>
            {targetRoles.length === 0 ? (
              <p className="text-sm text-muted-foreground">No target roles yet.</p>
            ) : (
              <ul className="flex flex-wrap gap-2">
                {targetRoles.map((role) => (
                  <li
                    key={role}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-brand-blue/30 bg-brand-blue/10 px-3 py-1.5 text-sm font-medium"
                  >
                    <Briefcase className="size-3.5 text-brand-teal" />
                    {role}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        {/* Stats */}
        <section className="grid gap-4 sm:grid-cols-3">
          <StatTile icon={Briefcase} label="Target roles" value={targetRoles.length} />
          <StatTile icon={Search} label="Postings found" value={results.length} />
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
                {results.length} found
              </span>
            </div>

            <Table>
              <TableHeader className="bg-muted/50">
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-5 text-xs uppercase tracking-wider text-muted-foreground">Role</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Location</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Source</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Posted</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Match</TableHead>
                  <TableHead className="pr-5" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {results.map((job) => (
                  <TableRow key={job.id} className="group">
                    <TableCell className="py-4 pl-5">
                      <div className="flex items-center gap-3">
                        <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-linear-to-br from-brand-blue/25 to-brand-green/25 text-sm font-semibold">
                          {job.company.charAt(0)}
                        </div>
                        <div>
                          <p className="font-medium">{job.title}</p>
                          <p className="flex items-center gap-1 text-xs text-muted-foreground">
                            <Building2 className="size-3" />
                            {job.company}
                          </p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      <span className="inline-flex items-center gap-1">
                        <MapPin className="size-3.5" />
                        {job.location}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="rounded-md border bg-muted/50 px-2 py-0.5 text-xs font-medium">
                        {job.source}
                      </span>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{job.postedAt}</TableCell>
                    <TableCell>
                      <MatchScore score={job.matchScore} />
                    </TableCell>
                    <TableCell className="pr-5 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        nativeButton={false}
                        render={<a href={job.url} target="_blank" rel="noopener noreferrer" />}
                        className="text-brand-teal opacity-70 group-hover:opacity-100"
                      >
                        View
                        <ExternalLink />
                      </Button>
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

function StatusPill({ running }: { running: boolean }) {
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
      {running ? "Agents running" : "Idle"}
    </span>
  )
}

function StatTile({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-4 rounded-2xl border bg-card p-5">
      <div className="flex size-11 items-center justify-center rounded-xl bg-linear-to-br from-brand-blue/20 to-brand-green/20 ring-1 ring-brand-teal/20">
        <Icon className="size-5 text-brand-teal" />
      </div>
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
      </div>
    </div>
  )
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

function MatchScore({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-linear-to-r from-brand-blue via-brand-teal to-brand-green"
          style={{ width: `${score}%` }}
        />
      </div>
      <span className="text-sm font-medium tabular-nums">{score}%</span>
    </div>
  )
}
