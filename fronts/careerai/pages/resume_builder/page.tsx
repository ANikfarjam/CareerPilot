"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import {
  Building2,
  Check,
  Copy,
  Download,
  ExternalLink,
  FileText,
  History,
  Lightbulb,
  LoaderCircle,
  Pencil,
  RotateCcw,
  Save,
  Search,
  Sparkles,
  TriangleAlert,
  X,
} from "lucide-react"

import { ChatPanel } from "@/components/chat-panel"
import { Markdown } from "@/components/markdown"
import { StatusPill } from "@/components/status-pill"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { useResumeChat, type PendingReply } from "@/hooks/use-resume-chat"
import {
  ApiError,
  buildResume,
  getDraft,
  listDrafts,
  listJobs,
  revertDraft,
  updateDraft,
  type DocTarget,
  type Job,
  type ResumeDraft,
  type ResumeDraftSummary,
} from "@/lib/api"
import { cn } from "@/lib/utils"

const TABS: { id: DocTarget; label: string; icon: typeof FileText }[] = [
  { id: "resume", label: "Resume", icon: FileText },
  { id: "side_projects", label: "Side projects", icon: Lightbulb },
]

export default function ResumeBuilderPage() {
  const searchParams = useSearchParams()

  // Jobs to tailor a resume to, best match first.
  const [jobs, setJobs] = useState<Job[] | null>(null)
  const [jobsError, setJobsError] = useState<string | null>(null)
  const [jobFilter, setJobFilter] = useState("")
  const [pickedJobId, setPickedJobId] = useState<string | null>(null)
  const jobId = pickedJobId ?? searchParams?.get("job") ?? jobs?.[0]?.id ?? null
  const job = jobs?.find((j) => j.id === jobId) ?? null

  // Drafts of the selected job; the newest opens unless another is picked.
  const [drafts, setDrafts] = useState<{ jobId: string; items: ResumeDraftSummary[] } | null>(null)
  const [pickedDraftId, setPickedDraftId] = useState<string | null>(null)
  const jobDrafts = drafts?.jobId === jobId ? drafts.items : null
  const draftId = (pickedDraftId && jobDrafts?.some((d) => d.id === pickedDraftId) ? pickedDraftId : null)
    ?? jobDrafts?.[0]?.id ?? null
  const [draft, setDraft] = useState<ResumeDraft | null>(null)
  const openDraft = draft?.id === draftId ? draft : null

  const [building, setBuilding] = useState<{ jobId: string; startedAt: number } | null>(null)
  const [buildError, setBuildError] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [tab, setTab] = useState<DocTarget>("resume")

  useEffect(() => {
    listJobs({ sort_by: "compatibility", order: "desc", limit: 200 })
      .then((page) => setJobs(page.items))
      .catch((e) => {
        setJobs([])
        setJobsError(errorMessage(e))
      })
  }, [])

  useEffect(() => {
    if (!jobId) return
    let stale = false
    listDrafts(jobId)
      .then((items) => !stale && setDrafts({ jobId, items }))
      .catch(() => !stale && setDrafts({ jobId, items: [] }))
    return () => {
      stale = true
    }
  }, [jobId])

  useEffect(() => {
    if (!draftId || draft?.id === draftId) return
    let stale = false
    getDraft(draftId)
      .then((d) => !stale && setDraft(d))
      .catch((e) => !stale && setBuildError(errorMessage(e)))
    return () => {
      stale = true
    }
  }, [draftId, draft?.id])

  useEffect(() => {
    if (!building) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [building])

  // A saved chat edit, revert or manual save: show it and bump the draft to the top of the list.
  const applyDraft = useCallback((updated: ResumeDraft) => {
    setDraft(updated)
    setDrafts((prev) =>
      prev && prev.jobId === updated.job_id
        ? { ...prev, items: [updated, ...prev.items.filter((d) => d.id !== updated.id)] }
        : prev,
    )
  }, [])

  const chat = useResumeChat(openDraft?.id ?? null, applyDraft)

  const handleBuild = async () => {
    if (!jobId) return
    setBuilding({ jobId, startedAt: Date.now() })
    setNow(Date.now())
    setBuildError(null)
    try {
      const report = await buildResume(jobId)
      const created = await getDraft(report.draft_id)
      setPickedDraftId(created.id)
      applyDraft(created)
      setTab("resume")
    } catch (e) {
      setBuildError(
        e instanceof ApiError && e.status === 409
          ? "Another agent run is using the model. Try again when it finishes."
          : errorMessage(e),
      )
    } finally {
      setBuilding(null)
    }
  }

  const filteredJobs = useMemo(() => {
    const q = jobFilter.trim().toLowerCase()
    if (!jobs || !q) return jobs
    return jobs.filter((j) => `${j.company_name} ${j.position}`.toLowerCase().includes(q))
  }, [jobs, jobFilter])

  const isBuilding = building !== null
  const statusLabel = isBuilding
    ? `Building resume · ${formatElapsed(now - building.startedAt)}`
    : chat.pending
      ? chat.pending.phase === "thinking" ? "Assistant thinking" : "Assistant writing"
      : openDraft
        ? `Draft saved ${formatDateTime(openDraft.update_at)}`
        : "No draft yet"

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
                <FileText className="size-3.5" />
                Resume builder
              </span>
              <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
                A resume for{" "}
                <span className="bg-linear-to-r from-brand-teal to-brand-green bg-clip-text text-transparent">
                  {job ? job.company_name : "every job"}
                </span>
              </h1>
              <p className="max-w-xl text-sm leading-relaxed text-muted-foreground sm:text-base">
                {job
                  ? `${job.position} · ${job.compatibility}/10 match. `
                  : "Pick a saved job. "}
                The agent writes a tailored resume and side projects from your knowledge base; then
                chat to adjust them.
              </p>
            </div>
            <div className="flex flex-col items-start gap-3 md:items-end">
              <StatusPill running={isBuilding || chat.pending !== null} label={statusLabel} />
              <Button
                size="lg"
                onClick={handleBuild}
                disabled={!jobId || isBuilding}
                className="h-12 rounded-xl bg-linear-to-r from-brand-blue via-brand-teal to-brand-green px-6 text-base font-semibold text-brand-navy shadow-lg shadow-brand-teal/25 transition hover:shadow-brand-teal/40 hover:brightness-110"
              >
                {isBuilding ? <LoaderCircle className="size-5 animate-spin" /> : <Sparkles className="size-5" />}
                {isBuilding ? "Building…" : jobDrafts?.length ? "Build a new draft" : "Build resume"}
              </Button>
            </div>
          </div>
          {buildError && <Banner className="mt-6">{buildError}</Banner>}
        </section>

        <div className="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)_360px]">
          {/* Jobs + drafts */}
          <aside className="flex flex-col gap-4">
            <section className="rounded-2xl border bg-card p-4">
              <h2 className="mb-3 text-sm font-semibold">Saved jobs</h2>
              <div className="relative mb-3">
                <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={jobFilter}
                  onChange={(e) => setJobFilter(e.target.value)}
                  placeholder="Filter jobs"
                  aria-label="Filter jobs"
                  className="pl-8"
                />
              </div>
              {jobsError && <Banner>Could not load jobs: {jobsError}</Banner>}
              {filteredJobs === null ? (
                <div className="space-y-2">
                  {[0, 1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-12 w-full rounded-lg" />
                  ))}
                </div>
              ) : filteredJobs.length === 0 ? (
                <div className="flex flex-col items-center gap-3 py-6 text-center">
                  <p className="text-sm text-muted-foreground">{jobFilter ? "No job matches." : "No saved jobs yet."}</p>
                  {!jobFilter && (
                    <Button variant="outline" size="sm" nativeButton={false} render={<Link href="/search/page" />}>
                      Go to search
                    </Button>
                  )}
                </div>
              ) : (
                <ul className="-mx-1 max-h-80 space-y-1 overflow-y-auto px-1 lg:max-h-[420px]">
                  {filteredJobs.map((j) => (
                    <li key={j.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setPickedJobId(j.id)
                          setPickedDraftId(null)
                        }}
                        className={cn(
                          "flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left transition",
                          j.id === jobId ? "bg-brand-teal/10 ring-1 ring-brand-teal/30" : "hover:bg-muted",
                        )}
                      >
                        <Building2 className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium">{j.position}</span>
                          <span className="block truncate text-xs text-muted-foreground">{j.company_name}</span>
                        </span>
                        <span className="rounded-full bg-muted px-1.5 py-0.5 text-xs tabular-nums text-muted-foreground">
                          {j.compatibility}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {jobId && (
              <section className="rounded-2xl border bg-card p-4">
                <h2 className="mb-3 text-sm font-semibold">Drafts for this job</h2>
                {jobDrafts === null ? (
                  <Skeleton className="h-10 w-full rounded-lg" />
                ) : jobDrafts.length === 0 ? (
                  <p className="text-sm text-muted-foreground">None yet. Build one above.</p>
                ) : (
                  <ul className="space-y-1">
                    {jobDrafts.map((d, i) => (
                      <li key={d.id}>
                        <button
                          type="button"
                          onClick={() => setPickedDraftId(d.id)}
                          className={cn(
                            "w-full rounded-lg px-2.5 py-2 text-left text-sm transition",
                            d.id === draftId ? "bg-brand-teal/10 ring-1 ring-brand-teal/30" : "hover:bg-muted",
                          )}
                        >
                          <span className="block font-medium">Draft {jobDrafts.length - i}</span>
                          <span className="block text-xs text-muted-foreground">
                            Edited {formatDateTime(d.update_at)}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            )}
          </aside>

          {/* Documents */}
          <DocumentPane
            draft={openDraft}
            loading={draftId !== null && openDraft === null}
            pending={chat.pending}
            tab={tab}
            onTab={setTab}
            onDraft={applyDraft}
            job={job}
          />

          {/* Chat */}
          {openDraft ? (
            <ChatPanel
              messages={openDraft.messages}
              pending={chat.pending}
              socketState={chat.socketState}
              error={chat.error}
              onSend={chat.send}
              className="h-[560px] lg:sticky lg:top-24 lg:h-[calc(100vh-8rem)]"
            />
          ) : (
            <section className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed p-6 text-center">
              <Sparkles className="size-6 text-muted-foreground" />
              <p className="max-w-xs text-sm text-muted-foreground">
                Build a resume first, then chat here to adjust it.
              </p>
            </section>
          )}
        </div>
      </main>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
// Resume / side projects
// ─────────────────────────────────────────────────────────

type DocumentPaneProps = {
  draft: ResumeDraft | null
  loading: boolean
  pending: PendingReply | null
  tab: DocTarget
  onTab: (tab: DocTarget) => void
  onDraft: (draft: ResumeDraft) => void
  job: Job | null
}

function DocumentPane({ draft, loading, pending, tab, onTab, onDraft, job }: DocumentPaneProps) {
  const [editing, setEditing] = useState<{ draftId: string; tab: DocTarget; text: string } | null>(null)
  const [showVersions, setShowVersions] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  if (loading || !draft) {
    return (
      <section className="flex min-h-[420px] flex-col rounded-2xl border bg-card p-6">
        {loading ? (
          <div className="space-y-3">
            <Skeleton className="h-8 w-1/2" />
            <Skeleton className="h-4 w-3/4" />
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-4 w-full" />
            ))}
          </div>
        ) : (
          <div className="m-auto flex max-w-sm flex-col items-center gap-3 text-center">
            <FileText className="size-6 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              {job
                ? "No resume for this job yet. Build one: it takes a minute or two on the local model."
                : "Pick a job to see its resume drafts."}
            </p>
          </div>
        )}
      </section>
    )
  }

  const streamed = pending?.[tab] ?? null
  const isEditingHere = editing?.draftId === draft.id && editing.tab === tab
  const text = streamed ?? draft[tab]
  const filename = `${slug(`${draft.company_name ?? "job"}-${draft.position ?? ""}`)}-${tab === "resume" ? "resume" : "side-projects"}.md`

  const run = async (action: () => Promise<ResumeDraft>) => {
    setBusy(true)
    setError(null)
    try {
      onDraft(await action())
      return true
    } catch (e) {
      setError(errorMessage(e))
      return false
    } finally {
      setBusy(false)
    }
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(draft[tab])
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      setError("Could not copy to the clipboard.")
    }
  }

  const download = () => {
    const url = URL.createObjectURL(new Blob([draft[tab]], { type: "text/markdown" }))
    const a = document.createElement("a")
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <section className="flex min-w-0 flex-col rounded-2xl border bg-card">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
        <div role="tablist" className="flex gap-1">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              role="tab"
              type="button"
              aria-selected={tab === id}
              onClick={() => onTab(id)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition",
                tab === id ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="size-4" />
              {label}
              {pending?.[id] != null && <span className="size-1.5 animate-pulse rounded-full bg-brand-teal" />}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          {job?.link && (
            <Button variant="ghost" size="sm" nativeButton={false} render={<a href={job.link} target="_blank" rel="noreferrer" />}>
              <ExternalLink />
              Posting
            </Button>
          )}
          <Button
            variant={showVersions ? "secondary" : "ghost"}
            size="sm"
            onClick={() => setShowVersions((v) => !v)}
            disabled={draft.versions.length === 0}
          >
            <History />
            {draft.versions.length}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setEditing({ draftId: draft.id, tab, text: draft[tab] })}
            disabled={isEditingHere || pending !== null}
          >
            <Pencil />
            Edit
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={copy} aria-label="Copy Markdown">
            {copied ? <Check /> : <Copy />}
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={download} aria-label="Download Markdown">
            <Download />
          </Button>
        </div>
      </header>

      {error && <Banner className="m-4 mb-0">{error}</Banner>}

      {showVersions && draft.versions.length > 0 && (
        <ol className="max-h-56 space-y-1 overflow-y-auto border-b bg-muted/30 p-3">
          {draft.versions
            .map((v, i) => ({ ...v, index: i }))
            .reverse()
            .map((v) => (
              <li key={v.index} className="flex items-center gap-3 rounded-lg px-2 py-1.5 text-sm hover:bg-muted">
                <span className="w-8 shrink-0 text-xs tabular-nums text-muted-foreground">v{v.index + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate">Before {v.note || "an edit"}</span>
                  <span className="block text-xs text-muted-foreground">{formatDateTime(v.at)}</span>
                </span>
                <Button
                  variant="outline"
                  size="xs"
                  disabled={busy || pending !== null}
                  onClick={() => run(() => revertDraft(draft.id, v.index))}
                >
                  <RotateCcw />
                  Restore
                </Button>
              </li>
            ))}
        </ol>
      )}

      <div className="relative flex-1 p-6 sm:p-8">
        {streamed !== null && (
          <span className="absolute top-3 right-3 inline-flex items-center gap-1.5 rounded-full border border-brand-teal/30 bg-brand-teal/10 px-2.5 py-0.5 text-xs font-medium text-brand-teal">
            <LoaderCircle className="size-3 animate-spin" />
            Editing…
          </span>
        )}
        {isEditingHere ? (
          <div className="flex h-full flex-col gap-3">
            <textarea
              value={editing.text}
              onChange={(e) => setEditing({ ...editing, text: e.target.value })}
              aria-label={`Edit ${tab === "resume" ? "resume" : "side projects"} Markdown`}
              className="min-h-[480px] flex-1 resize-y rounded-md border border-input bg-transparent p-3 font-mono text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
            />
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setEditing(null)} disabled={busy}>
                <X />
                Cancel
              </Button>
              <Button
                onClick={async () => {
                  if (await run(() => updateDraft(draft.id, { [tab]: editing.text }))) setEditing(null)
                }}
                disabled={busy || editing.text === draft[tab]}
              >
                {busy ? <LoaderCircle className="animate-spin" /> : <Save />}
                Save
              </Button>
            </div>
          </div>
        ) : (
          <article className={cn("text-sm leading-relaxed", streamed !== null && "opacity-90")}>
            <Markdown variant="document">{text}</Markdown>
          </article>
        )}
      </div>
    </section>
  )
}

// ─────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────

function Banner({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive",
        className,
      )}
    >
      <TriangleAlert className="mt-0.5 size-4 shrink-0" />
      <p>{children}</p>
    </div>
  )
}

function errorMessage(e: unknown) {
  return e instanceof Error ? e.message : String(e)
}

function slug(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
}

function formatElapsed(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`
}
