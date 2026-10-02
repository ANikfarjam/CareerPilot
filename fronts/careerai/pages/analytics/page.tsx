"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ReferenceArea,
  XAxis,
  YAxis,
} from "recharts"
import {
  Briefcase,
  CalendarCheck,
  ChartColumn,
  ExternalLink,
  Gauge,
  Hammer,
  LoaderCircle,
  Send,
  Sparkles,
  Target,
  TriangleAlert,
} from "lucide-react"

import { Markdown } from "@/components/markdown"
import { StatTile } from "@/components/stat-tile"
import { StatusPill } from "@/components/status-pill"
import { Button } from "@/components/ui/button"
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  ApiError,
  getAnalytics,
  getAnalyticsRun,
  startAnalyticsRun,
  type AnalyticsReport,
  type AnalyticsRun,
  type Effort,
  type WeeklyRow,
} from "@/lib/api"
import { cn } from "@/lib/utils"

const RUN_ID_KEY = "careerai.analyticsRunId"
const POLL_MS = 3000
const NEAR_MISS = [5, 8] // compatibility band the agent calls near-miss (agents/analytics/agent.py)

// Categorical slots, fixed order, validated for CVD separation on the light and dark card
// surfaces. The same entity keeps the same color on every chart.
const SLOT = {
  blue: { light: "#2a78d6", dark: "#3987e5" },
  orange: { light: "#eb6834", dark: "#d95926" },
  aqua: { light: "#1baf7a", dark: "#199e70" },
  yellow: { light: "#eda100", dark: "#c98500" },
}

const funnelConfig = { count: { label: "Jobs", theme: SLOT.blue } } satisfies ChartConfig

const weeklyConfig = {
  found: { label: "Found only", theme: SLOT.blue },
  applied: { label: "Applied", theme: SLOT.orange },
  interviewing: { label: "Interviewing", theme: SLOT.aqua },
  closed: { label: "Dropped / denied", theme: SLOT.yellow },
} satisfies ChartConfig

const stageConfig = {
  found: { label: "Found", theme: SLOT.blue },
  applied: { label: "Applied", theme: SLOT.orange },
  interview: { label: "Interview", theme: SLOT.aqua },
} satisfies ChartConfig

const gapConfig = {
  jobs: { label: "Missing in", theme: SLOT.blue },
  required_in: { label: "Required in", theme: SLOT.orange },
} satisfies ChartConfig

const STAGE_LABELS: Record<string, string> = {
  found: "Found",
  applied: "Applied",
  interview: "Interview",
  interview_done: "Interview done",
}

const ACTION_LABELS: Record<string, string> = {
  searched: "Found",
  applied: "Applied",
  drop: "Dropped",
  interview_scheduled: "Interview scheduled",
  interview_inprogress: "Interviewing",
  interview_done: "Interview done",
  denied: "Denied",
}

const EFFORT_STYLE: Record<Effort, string> = {
  weekend: "border-brand-green/30 bg-brand-green/10 text-brand-green",
  "1-2 weeks": "border-brand-teal/30 bg-brand-teal/10 text-brand-teal",
  "1 month+": "border-brand-blue/30 bg-brand-blue/10 text-brand-blue",
}

export default function AnalyticsPage() {
  // Chart tables: always fresh from GET /agents/analytics.
  const [report, setReport] = useState<AnalyticsReport | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  // null while loading; false when no job has been saved yet (or the API is unreachable).
  const [hasJobs, setHasJobs] = useState<boolean | null>(null)
  // AI results: the last analytics run, remembered across reloads.
  const [runId, setRunId] = useState<string | null>(() => readRunId())
  const [run, setRun] = useState<AnalyticsRun | null>(null)
  const [runError, setRunError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [now, setNow] = useState(() => Date.now())

  const isRunning = starting || run?.status === "queued" || run?.status === "running"
  const insights = run?.status === "succeeded" ? run.report : null

  useEffect(() => {
    getAnalytics()
      .then((r) => {
        setReport(r)
        setHasJobs(r.total_jobs > 0)
      })
      .catch((e) => {
        setLoadError(e instanceof Error ? e.message : String(e))
        setHasJobs(false)
      })
  }, [])

  // Poll the run until it finishes.
  useEffect(() => {
    if (!runId) return
    let stopped = false
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      try {
        const next = await getAnalyticsRun(runId)
        if (stopped) return
        setRun(next)
        if (next.status === "queued" || next.status === "running") timer = setTimeout(poll, POLL_MS)
      } catch (e) {
        if (stopped) return
        if (e instanceof ApiError && e.status === 404) {
          // Runs live in the API's memory; it was restarted.
          writeRunId(null)
          setRunId(null)
          setRun(null)
        } else {
          setRunError(e instanceof Error ? e.message : String(e))
          timer = setTimeout(poll, POLL_MS)
        }
      }
    }
    poll()
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [runId])

  // Tick the elapsed-time counter while the agent works.
  useEffect(() => {
    if (!isRunning) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [isRunning])

  const handleRun = async () => {
    setStarting(true)
    setRunError(null)
    try {
      const started = await startAnalyticsRun("sandbox-cpu")
      writeRunId(started.id)
      setRun(started)
      setRunId(started.id)
      setNow(Date.now())
    } catch (e) {
      setRunError(
        e instanceof ApiError && e.status === 409
          ? "Another agent run is in progress. Try again when it finishes."
          : e instanceof Error
            ? e.message
            : String(e),
      )
    } finally {
      setStarting(false)
    }
  }

  const statusLabel = isRunning
    ? `Analyzing · ${formatElapsed(now - Date.parse(run?.started_at ?? run?.created_at ?? new Date(now).toISOString()))}`
    : run?.status === "failed"
      ? "Last run failed"
      : insights
        ? `Analyzed ${formatDateTime(insights.generated_at)}`
        : "Not analyzed yet"

  return (
    <div className="relative flex min-h-full flex-1 flex-col">
      {/* Brand glow */}
      <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[480px] bg-[radial-gradient(60%_60%_at_20%_0%,color-mix(in_oklch,var(--brand-blue)_30%,transparent),transparent),radial-gradient(50%_50%_at_85%_10%,color-mix(in_oklch,var(--brand-green)_18%,transparent),transparent)]" />

      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-4 py-8 sm:px-6 sm:py-10">
        {/* Header */}
        <section className="rounded-2xl border bg-card/60 p-6 shadow-xl shadow-black/20 backdrop-blur sm:p-8">
          <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
            <div className="space-y-3">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-teal/30 bg-brand-teal/10 px-3 py-1 text-xs font-medium text-brand-teal">
                <ChartColumn className="size-3.5" />
                Search analytics
              </span>
              <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
                How your search is{" "}
                <span className="bg-linear-to-r from-brand-teal to-brand-green bg-clip-text text-transparent">
                  going
                </span>
              </h1>
              <p className="max-w-xl text-sm leading-relaxed text-muted-foreground sm:text-base">
                Charts update from every saved job. Run the AI analysis to find near-miss jobs,
                the skills they ask for, and side projects that close the gap.
              </p>
            </div>
            <div className="flex flex-col items-start gap-3 md:items-end">
              <StatusPill running={isRunning} label={statusLabel} />
              <Button
                size="lg"
                onClick={handleRun}
                disabled={isRunning || !hasJobs}
                className="h-12 rounded-xl bg-linear-to-r from-brand-blue via-brand-teal to-brand-green px-6 text-base font-semibold text-brand-navy shadow-lg shadow-brand-teal/25 transition hover:shadow-brand-teal/40 hover:brightness-110"
              >
                {isRunning ? <LoaderCircle className="size-5 animate-spin" /> : <Sparkles className="size-5" />}
                {isRunning ? "Analyzing…" : insights ? "Re-run AI analysis" : "Run AI analysis"}
              </Button>
            </div>
          </div>
          {runError && <Banner className="mt-6">{runError}</Banner>}
          {run?.status === "failed" && run.error && <Banner className="mt-6">The analysis failed: {run.error}</Banner>}
        </section>

        {loadError && <Banner>Could not load analytics: {loadError}</Banner>}
        {hasJobs === null ? (
          <LoadingCharts />
        ) : !hasJobs || !report ? (
          <NoJobsCards />
        ) : (
          <>
            <KpiRow report={report} />
            <ChartsGrid report={report} />
            <InsightsSection insights={insights} running={isRunning} />
          </>
        )}
      </main>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
// Charts (host tables)
// ─────────────────────────────────────────────────────────

function KpiRow({ report }: { report: AnalyticsReport }) {
  const stage = (name: string) => report.tables.funnel.find((r) => r.stage === name)
  const found = stage("found")?.count ?? report.total_jobs
  const applied = stage("applied")
  const interview = stage("interview")
  const scored = report.tables.compatibility.reduce((sum, r) => sum + r.found, 0)
  const avg = scored
    ? report.tables.compatibility.reduce((sum, r) => sum + r.compatibility * r.found, 0) / scored
    : null

  return (
    <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatTile icon={Briefcase} label="Jobs found" value={found} />
      <StatTile icon={Send} label="Applied" value={applied?.count ?? 0} hint={applied && `${formatPct(applied.rate)} of found`} />
      <StatTile icon={CalendarCheck} label="Interviews" value={interview?.count ?? 0} hint={interview && `${formatPct(interview.rate)} of found`} />
      <StatTile icon={Gauge} label="Avg. compatibility" value={avg === null ? "—" : `${avg.toFixed(1)}/10`} />
    </section>
  )
}

function ChartsGrid({ report }: { report: AnalyticsReport }) {
  const { funnel, weekly, compatibility, by_job_type, by_company } = report.tables
  const funnelData = funnel.map((r) => ({
    ...r,
    label: STAGE_LABELS[r.stage] ?? r.stage,
    display: `${r.count} · ${formatPct(r.rate)}`,
  }))
  const weeklyData = useMemo(() => weekly.map(bucketWeek), [weekly])
  const jobTypeData = by_job_type.map((r) => ({ ...r, label: titleCase(r.job_type) }))

  return (
    <section className="grid gap-6 lg:grid-cols-2">
      <ChartCard title="Funnel" description="How far found jobs get, with the share of all found jobs.">
        <ChartContainer config={funnelConfig} className="aspect-auto h-64 w-full">
          <BarChart data={funnelData} layout="vertical" margin={{ left: 8, right: 72 }}>
            <YAxis dataKey="label" type="category" tickLine={false} axisLine={false} width={104} />
            <XAxis type="number" hide />
            <ChartTooltip cursor={false} content={<ChartTooltipContent hideIndicator />} />
            <Bar dataKey="count" fill="var(--color-count)" radius={4} barSize={28}>
              <LabelList dataKey="display" position="right" className="fill-foreground" />
            </Bar>
          </BarChart>
        </ChartContainer>
      </ChartCard>

      <ChartCard title="Weekly activity" description="Jobs by the week they were last updated, grouped by status.">
        <ChartContainer config={weeklyConfig} className="aspect-auto h-64 w-full">
          <BarChart data={weeklyData}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="week" tickLine={false} axisLine={false} tickFormatter={formatWeek} minTickGap={16} />
            <YAxis tickLine={false} axisLine={false} allowDecimals={false} width={32} />
            <ChartTooltip content={<ChartTooltipContent labelFormatter={(_, p) => `Week of ${formatWeek(p?.[0]?.payload?.week)}`} />} />
            <ChartLegend content={<ChartLegendContent />} itemSorter={null} />
            <Bar dataKey="found" stackId="a" fill="var(--color-found)" stroke="var(--card)" strokeWidth={1} />
            <Bar dataKey="applied" stackId="a" fill="var(--color-applied)" stroke="var(--card)" strokeWidth={1} />
            <Bar dataKey="interviewing" stackId="a" fill="var(--color-interviewing)" stroke="var(--card)" strokeWidth={1} />
            <Bar dataKey="closed" stackId="a" fill="var(--color-closed)" stroke="var(--card)" strokeWidth={1} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ChartContainer>
      </ChartCard>

      <ChartCard
        title="Compatibility"
        description={`Fit score of every job (0-10). The shaded ${NEAR_MISS[0]}-${NEAR_MISS[1]} band is where near-miss jobs live.`}
      >
        <ChartContainer config={stageConfig} className="aspect-auto h-64 w-full">
          <BarChart data={compatibility} barGap={2}>
            <CartesianGrid vertical={false} />
            <ReferenceArea x1={NEAR_MISS[0]} x2={NEAR_MISS[1]} fill="var(--muted-foreground)" fillOpacity={0.08} />
            <XAxis dataKey="compatibility" tickLine={false} axisLine={false} />
            <YAxis tickLine={false} axisLine={false} allowDecimals={false} width={32} />
            <ChartTooltip content={<ChartTooltipContent labelFormatter={(_, p) => `Score ${p?.[0]?.payload?.compatibility}/10`} />} />
            <ChartLegend content={<ChartLegendContent />} itemSorter={null} />
            <Bar dataKey="found" fill="var(--color-found)" radius={[4, 4, 0, 0]} />
            <Bar dataKey="applied" fill="var(--color-applied)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ChartContainer>
      </ChartCard>

      <ChartCard title="Work type" description="Found, applied and interviewed jobs by work arrangement.">
        <ChartContainer config={stageConfig} className="aspect-auto h-64 w-full">
          <BarChart data={jobTypeData} barGap={2}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="label" tickLine={false} axisLine={false} />
            <YAxis tickLine={false} axisLine={false} allowDecimals={false} width={32} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <ChartLegend content={<ChartLegendContent />} itemSorter={null} />
            <Bar dataKey="found" fill="var(--color-found)" radius={[4, 4, 0, 0]} />
            <Bar dataKey="applied" fill="var(--color-applied)" radius={[4, 4, 0, 0]} />
            <Bar dataKey="interview" fill="var(--color-interview)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ChartContainer>
      </ChartCard>

      <section className="min-w-0 overflow-hidden rounded-2xl border bg-card lg:col-span-2">
        <div className="px-5 py-4">
          <h2 className="font-medium">Top companies</h2>
          <p className="text-sm text-muted-foreground">Companies with the most found jobs.</p>
        </div>
        <Table>
          <TableHeader className="bg-muted/50">
            <TableRow className="hover:bg-transparent">
              <Th className="pl-5">Company</Th>
              <Th className="text-right">Found</Th>
              <Th className="text-right">Applied</Th>
              <Th className="text-right">Interview</Th>
              <Th className="pr-5">Avg. compatibility</Th>
            </TableRow>
          </TableHeader>
          <TableBody>
            {by_company.slice(0, 10).map((c) => (
              <TableRow key={c.company_name}>
                <TableCell className="pl-5 font-medium">{c.company_name}</TableCell>
                <TableCell className="text-right tabular-nums">{c.found}</TableCell>
                <TableCell className="text-right tabular-nums">{c.applied}</TableCell>
                <TableCell className="text-right tabular-nums">{c.interview}</TableCell>
                <TableCell className="pr-5">
                  {c.avg_compatibility === null ? "—" : <ScoreBar score={c.avg_compatibility} />}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
    </section>
  )
}

// ─────────────────────────────────────────────────────────
// AI insights (analytics run)
// ─────────────────────────────────────────────────────────

function InsightsSection({ insights, running }: { insights: AnalyticsReport | null; running: boolean }) {
  if (!insights) {
    return (
      <section className="rounded-2xl border bg-card p-6">
        <SectionTitle icon={Sparkles}>AI insights</SectionTitle>
        {running ? (
          <div className="mt-5 space-y-3">
            <p className="text-sm text-muted-foreground">
              The agent is analyzing your jobs in the sandbox. This takes a few minutes.
            </p>
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-11/12" />
            <Skeleton className="h-4 w-4/5" />
            <div className="grid gap-4 pt-3 md:grid-cols-3">
              <Skeleton className="h-32" />
              <Skeleton className="h-32" />
              <Skeleton className="h-32" />
            </div>
          </div>
        ) : (
          <div className="mt-5 flex flex-col items-center gap-3 rounded-xl border border-dashed py-10 text-center">
            <Sparkles className="size-6 text-muted-foreground" />
            <p className="max-w-md text-sm text-muted-foreground">
              Run the AI analysis to get a written review of your search, the near-miss jobs
              you almost qualify for, and side projects that close those skill gaps.
            </p>
          </div>
        )}
      </section>
    )
  }

  const gapData = insights.skill_gaps.slice(0, 10)

  return (
    <>
      {insights.errors.map((error) => (
        <Banner key={error}>{error}</Banner>
      ))}

      <section className="rounded-2xl border bg-card p-6">
        <SectionTitle icon={Sparkles}>AI insights</SectionTitle>
        <div className="mt-4 space-y-4 text-sm leading-relaxed">
          <Markdown>
            {insights.analysis}
          </Markdown>
          <div className="rounded-xl border border-brand-teal/30 bg-brand-teal/5 p-4">
            <p className="mb-1 text-xs font-medium uppercase tracking-wider text-brand-teal">Conclusion</p>
            <Markdown>
              {insights.conclusion}
            </Markdown>
          </div>
        </div>
      </section>

      {gapData.length > 0 && (
        <ChartCard
          title="Skill gaps"
          description="Skills the near-miss jobs ask for that you're missing. Required matters most."
        >
          <ChartContainer config={gapConfig} className="aspect-auto w-full" style={{ height: 56 + gapData.length * 40 }}>
            <BarChart data={gapData} layout="vertical" barGap={2} margin={{ left: 8, right: 24 }}>
              <CartesianGrid horizontal={false} />
              <YAxis dataKey="skill" type="category" tickLine={false} axisLine={false} width={128} />
              <XAxis type="number" tickLine={false} axisLine={false} allowDecimals={false} />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    className="max-w-72"
                    labelFormatter={(_, p) => {
                      const gap = p?.[0]?.payload
                      return (
                        <div>
                          <p>{gap?.skill}</p>
                          {gap?.companies && <p className="font-normal text-muted-foreground">{gap.companies}</p>}
                        </div>
                      )
                    }}
                  />
                }
              />
              <ChartLegend content={<ChartLegendContent />} itemSorter={null} />
              <Bar dataKey="jobs" fill="var(--color-jobs)" radius={[0, 4, 4, 0]} barSize={12} />
              <Bar dataKey="required_in" fill="var(--color-required_in)" radius={[0, 4, 4, 0]} barSize={12} />
            </BarChart>
          </ChartContainer>
        </ChartCard>
      )}

      <section className="min-w-0 overflow-hidden rounded-2xl border bg-card">
        <div className="flex items-center justify-between px-5 py-4">
          <div>
            <h2 className="flex items-center gap-2 font-medium">
              <Target className="size-4 text-brand-teal" />
              Near-miss jobs
            </h2>
            <p className="text-sm text-muted-foreground">
              Compatibility {NEAR_MISS[0]}-{NEAR_MISS[1]}, but missing at least one required skill.
            </p>
          </div>
          <span className="rounded-full bg-brand-teal/10 px-2.5 py-0.5 text-xs font-medium text-brand-teal">
            {insights.near_miss_jobs.length} jobs
          </span>
        </div>
        {insights.near_miss_jobs.length === 0 ? (
          <p className="border-t py-12 text-center text-sm text-muted-foreground">No near-miss jobs. Nice.</p>
        ) : (
          <Table>
            <TableHeader className="bg-muted/50">
              <TableRow className="hover:bg-transparent">
                <Th className="pl-5">Role</Th>
                <Th>Compatibility</Th>
                <Th>Status</Th>
                <Th>Missing required skills</Th>
                <Th className="pr-5" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {insights.near_miss_jobs.map((job, i) => (
                <TableRow key={`${job.company_name}-${job.position}-${i}`} className="group">
                  <TableCell className="py-4 pl-5">
                    <p className="font-medium">{job.position}</p>
                    <p className="text-xs text-muted-foreground">{job.company_name}</p>
                  </TableCell>
                  <TableCell>
                    <ScoreBar score={job.compatibility} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">{ACTION_LABELS[job.action] ?? job.action}</TableCell>
                  <TableCell className="whitespace-normal">
                    <SkillChips skills={splitList(job.missing_required)} />
                  </TableCell>
                  <TableCell className="pr-5 text-right">
                    {job.link && (
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
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>

      {insights.projects.length > 0 && (
        <section className="space-y-4">
          <SectionTitle icon={Hammer}>Side projects to close the gaps</SectionTitle>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {insights.projects.map((p) => (
              <article key={p.title} className="flex flex-col gap-3 rounded-2xl border bg-card p-5">
                <div className="flex items-start justify-between gap-3">
                  <h3 className="font-medium leading-snug">{p.title}</h3>
                  <span className={cn("shrink-0 rounded-full border px-2.5 py-0.5 text-xs font-medium", EFFORT_STYLE[p.effort])}>
                    {p.effort}
                  </span>
                </div>
                <SkillChips skills={p.skills} />
                <p className="text-sm leading-relaxed">{p.description}</p>
                <p className="mt-auto border-t pt-3 text-xs leading-relaxed text-muted-foreground">
                  <span className="font-medium text-foreground">Why: </span>
                  {p.why}
                </p>
              </article>
            ))}
          </div>
        </section>
      )}
    </>
  )
}

// ─────────────────────────────────────────────────────────
// Small pieces
// ─────────────────────────────────────────────────────────

function ChartCard({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <section className="min-w-0 rounded-2xl border bg-card p-5">
      <h2 className="font-medium">{title}</h2>
      {description ? <p className="mb-4 text-sm text-muted-foreground">{description}</p> : <div className="mb-4" />}
      {children}
    </section>
  )
}

function SectionTitle({ icon: Icon, children }: { icon: React.ComponentType<{ className?: string }>; children: React.ReactNode }) {
  return (
    <h2 className="flex items-center gap-2 font-medium">
      <Icon className="size-4 text-brand-teal" />
      {children}
    </h2>
  )
}

function Th({ className, children }: { className?: string; children?: React.ReactNode }) {
  return <TableHead className={cn("text-xs uppercase tracking-wider text-muted-foreground", className)}>{children}</TableHead>
}

function SkillChips({ skills }: { skills: string[] }) {
  return (
    <ul className="flex flex-wrap gap-1.5">
      {skills.map((skill) => (
        <li key={skill} className="rounded-md border border-brand-blue/30 bg-brand-blue/10 px-2 py-0.5 text-xs font-medium">
          {skill}
        </li>
      ))}
    </ul>
  )
}

function ScoreBar({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-linear-to-r from-brand-blue via-brand-teal to-brand-green"
          style={{ width: `${score * 10}%` }}
        />
      </div>
      <span className="text-sm font-medium tabular-nums">{score}</span>
    </div>
  )
}

function Banner({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300",
        className,
      )}
    >
      <TriangleAlert className="mt-0.5 size-4 shrink-0" />
      <p>{children}</p>
    </div>
  )
}

function LoadingCharts() {
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-22 rounded-2xl" />
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-80 rounded-2xl" />
        ))}
      </div>
    </>
  )
}

// Same cards as the loaded page, each asking for a first search instead of showing data.
function NoJobsCards() {
  const note = "Please run your first search for the analytics to work."
  return (
    <>
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile icon={Briefcase} label="Jobs found" value="—" />
        <StatTile icon={Send} label="Applied" value="—" />
        <StatTile icon={CalendarCheck} label="Interviews" value="—" />
        <StatTile icon={Gauge} label="Avg. compatibility" value="—" />
      </section>
      <section className="grid gap-6 lg:grid-cols-2">
        {["Funnel", "Weekly activity", "Compatibility", "Work type"].map((title) => (
          <ChartCard key={title} title={title}>
            <NoJobsNote>{note}</NoJobsNote>
          </ChartCard>
        ))}
        <div className="lg:col-span-2">
          <ChartCard title="Top companies">
            <NoJobsNote>{note}</NoJobsNote>
          </ChartCard>
        </div>
      </section>
      <section className="rounded-2xl border bg-card p-6">
        <SectionTitle icon={Sparkles}>AI insights</SectionTitle>
        <div className="mt-5">
          <NoJobsNote>Please run your first search to generate insights.</NoJobsNote>
        </div>
      </section>
    </>
  )
}

function NoJobsNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed py-10 text-center">
      <ChartColumn className="size-6 text-muted-foreground" />
      <p className="max-w-xs text-sm text-muted-foreground">{children}</p>
      <Button variant="outline" size="sm" nativeButton={false} render={<Link href="/search/page" />}>
        Go to search
      </Button>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────

// Collapses the 7 statuses into 4 series; 7 categorical colors in one stack are unreadable.
function bucketWeek(row: WeeklyRow) {
  return {
    week: row.week,
    found: row.searched,
    applied: row.applied,
    interviewing: row.interview_scheduled + row.interview_inprogress + row.interview_done,
    closed: row.drop + row.denied,
  }
}

function splitList(value: string | null) {
  return value ? value.split(";").map((s) => s.trim()).filter(Boolean) : []
}

function titleCase(value: string) {
  return value.replace(/[_-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatPct(rate: number) {
  return `${Math.round(rate * 100)}%`
}

function formatWeek(value: string | undefined) {
  return value ? new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : ""
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
}

function formatElapsed(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`
}

// localStorage can throw (private mode, blocked storage); the run id is only a convenience.
function readRunId() {
  try {
    return typeof window === "undefined" ? null : window.localStorage.getItem(RUN_ID_KEY)
  } catch {
    return null
  }
}

function writeRunId(id: string | null) {
  try {
    if (id) window.localStorage.setItem(RUN_ID_KEY, id)
    else window.localStorage.removeItem(RUN_ID_KEY)
  } catch {
    // ignore
  }
}
