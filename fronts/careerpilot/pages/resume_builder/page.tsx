"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useSearchParams } from "next/navigation"
import {
  ArrowLeft,
  Check,
  CloudUpload,
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
  Sparkles,
  Table2,
  TriangleAlert,
  X,
} from "lucide-react"

import { ChatPanel } from "@/components/chat-panel"
import { Markdown } from "@/components/markdown"
import { JobsTable } from "@/components/resume/jobs-table"
import { StatusPill } from "@/components/status-pill"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useGoogleDrive, type GoogleDrive } from "@/hooks/use-google-drive"
import { useResumeChat, type PendingReply } from "@/hooks/use-resume-chat"
import {
  ApiError,
  buildResume,
  clearDraftChat,
  exportDraftToDrive,
  getDraft,
  listDrafts,
  listJobs,
  revertDraft,
  updateDraft,
  updateJobAction,
  type Action,
  type DocTarget,
  type DriveFile,
  type Job,
  type ResumeDraft,
  type ResumeDraftSummary,
} from "@/lib/api"
import { cn } from "@/lib/utils"

const TABS: { id: DocTarget; label: string; icon: typeof FileText }[] = [
  { id: "resume", label: "Resume", icon: FileText },
  { id: "side_projects", label: "Side projects", icon: Lightbulb },
]

type View = "jobs" | "editor"

export default function ResumeBuilderPage() {
  const searchParams = useSearchParams()
  const [view, setView] = useState<View>(searchParams?.get("job") ? "editor" : "jobs")

  // Jobs to tailor a resume to, best match first.
  const [jobs, setJobs] = useState<Job[] | null>(null)
  const [jobsError, setJobsError] = useState<string | null>(null)
  const [jobFilter, setJobFilter] = useState("")
  const [pickedJobId, setPickedJobId] = useState<string | null>(null)
  const jobId = pickedJobId ?? searchParams?.get("job") ?? jobs?.[0]?.id ?? null
  const job = jobs?.find((j) => j.id === jobId) ?? null

  // Every job's draft count, for the Jobs table.
  const [allDrafts, setAllDrafts] = useState<ResumeDraftSummary[] | null>(null)

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
    listDrafts()
      .then(setAllDrafts)
      .catch(() => setAllDrafts([]))
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
    setAllDrafts((prev) => prev && [updated, ...prev.filter((d) => d.id !== updated.id)])
  }, [])

  const chat = useResumeChat(openDraft?.id ?? null, applyDraft)

  const clearChat = async () => {
    if (!openDraft || !window.confirm("Clear this draft's chat? Your resume and side projects are kept.")) return
    try {
      applyDraft(await clearDraftChat(openDraft.id))
    } catch (e) {
      setBuildError(errorMessage(e))
    }
  }
  const drive = useGoogleDrive()

  const openJob = (id: string) => {
    setPickedJobId(id)
    setPickedDraftId(null)
    setView("editor")
  }

  const handleBuild = async (buildJobId: string | null = jobId) => {
    if (!buildJobId) return
    openJob(buildJobId)
    setBuilding({ jobId: buildJobId, startedAt: Date.now() })
    setNow(Date.now())
    setBuildError(null)
    try {
      const report = await buildResume(buildJobId)
      const created = await getDraft(report.draft_id)
      // The job's draft list may not have loaded yet if the build started from the Jobs table.
      setDrafts((prev) => (prev?.jobId === buildJobId ? prev : { jobId: buildJobId, items: [] }))
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

  // Optimistic: show the new status right away, put the old one back if the API refuses.
  const changeAction = async (target: Job, next: Action) => {
    const setJobAction = (value: Action) =>
      setJobs((list) => list && list.map((j) => (j.id === target.id ? { ...j, action: value } : j)))
    setJobAction(next)
    try {
      await updateJobAction(target.id, next)
    } catch (e) {
      setJobAction(target.action)
      setJobsError(errorMessage(e))
    }
  }

  const filteredJobs = useMemo(() => {
    const q = jobFilter.trim().toLowerCase()
    if (!jobs || !q) return jobs
    return jobs.filter((j) => `${j.company_name} ${j.position}`.toLowerCase().includes(q))
  }, [jobs, jobFilter])

  const draftCounts = useMemo(() => {
    if (!allDrafts) return null
    const counts: Record<string, number> = {}
    for (const d of allDrafts) counts[d.job_id] = (counts[d.job_id] ?? 0) + 1
    return counts
  }, [allDrafts])

  // "Draft N" counts a job's drafts by creation (oldest = 1), so a label never shifts after an
  // edit; the Drive export names its docs the same way.
  const draftNumbers = useMemo(() => {
    const byCreation = [...(jobDrafts ?? [])].sort((a, b) => a.created_at.localeCompare(b.created_at))
    return Object.fromEntries(byCreation.map((d, i) => [d.id, i + 1]))
  }, [jobDrafts])
  const draftItems = useMemo(
    () => Object.fromEntries((jobDrafts ?? []).map((d) => [d.id, `Draft ${draftNumbers[d.id]} · Edited ${formatDateTime(d.update_at)}`])),
    [jobDrafts, draftNumbers],
  )

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
                onClick={() => handleBuild()}
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

        <Tabs value={view} onValueChange={(v) => setView(v as View)} className="gap-6">
          <TabsList variant="line" className="w-full justify-start border-b">
            <TabsTrigger value="jobs" className="flex-none px-3">
              <Table2 />
              Jobs
            </TabsTrigger>
            <TabsTrigger value="editor" className="flex-none px-3" disabled={!job}>
              <Pencil />
              Editor
              {job && <span className="max-w-48 truncate text-muted-foreground">· {job.company_name}</span>}
            </TabsTrigger>
          </TabsList>

          {/* Jobs */}
          <TabsContent value="jobs" className="space-y-4">
            {jobsError && <Banner>{jobsError}</Banner>}
            <JobsTable
              jobs={filteredJobs}
              filter={jobFilter}
              onFilter={setJobFilter}
              selectedId={jobId}
              draftCounts={draftCounts}
              onOpen={(j) => openJob(j.id)}
              onBuild={(j) => handleBuild(j.id)}
              building={isBuilding}
              onAction={changeAction}
            />
          </TabsContent>

          {/* Resume + chat */}
          <TabsContent value="editor" className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="ghost" size="sm" onClick={() => setView("jobs")}>
                <ArrowLeft />
                Jobs
              </Button>
              {job && (
                <p className="min-w-0 flex-1 truncate text-sm">
                  <span className="font-medium">{job.position}</span>
                  <span className="text-muted-foreground"> · {job.company_name}</span>
                </p>
              )}
              {jobDrafts === null ? (
                <Skeleton className="h-8 w-64 rounded-md" />
              ) : jobDrafts.length > 0 && draftId ? (
                <Select items={draftItems} value={draftId} onValueChange={(v) => v && setPickedDraftId(v as string)}>
                  <SelectTrigger size="sm" className="w-64" aria-label="Draft">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {jobDrafts.map((d) => (
                      <SelectItem key={d.id} value={d.id}>
                        {draftItems[d.id]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : null}
              {drive.status?.connected && (
                <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                  <CloudUpload className="size-3.5" />
                  Drive: {drive.status.email ?? "connected"}
                  <Button variant="link" size="xs" className="h-auto px-1 text-xs" onClick={() => drive.disconnect()}>
                    Disconnect
                  </Button>
                </span>
              )}
            </div>

            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
              <DocumentPane
                draft={openDraft}
                draftNumber={draftId ? draftNumbers[draftId] : undefined}
                loading={draftId !== null && openDraft === null}
                pending={chat.pending}
                tab={tab}
                onTab={setTab}
                onDraft={applyDraft}
                job={job}
                drive={drive}
              />

              {openDraft ? (
                <ChatPanel
                  messages={openDraft.messages}
                  pending={chat.pending}
                  socketState={chat.socketState}
                  error={chat.error}
                  onSend={chat.send}
                  onClear={clearChat}
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
          </TabsContent>
        </Tabs>
      </main>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
// Resume / side projects
// ─────────────────────────────────────────────────────────

type DocumentPaneProps = {
  draft: ResumeDraft | null
  draftNumber?: number
  loading: boolean
  pending: PendingReply | null
  tab: DocTarget
  onTab: (tab: DocTarget) => void
  onDraft: (draft: ResumeDraft) => void
  job: Job | null
  drive: GoogleDrive
}

function DocumentPane({ draft, draftNumber, loading, pending, tab, onTab, onDraft, job, drive }: DocumentPaneProps) {
  const [editing, setEditing] = useState<{ draftId: string; tab: DocTarget; text: string } | null>(null)
  const [showVersions, setShowVersions] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  // Google Docs this session exported, by `${draftId}:${tab}`.
  const [driveFiles, setDriveFiles] = useState<Record<string, DriveFile>>({})
  const [exporting, setExporting] = useState(false)

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

  const driveKey = `${draft.id}:${tab}`
  const driveFile = driveFiles[driveKey]

  // Not connected yet: Google's sign-in opens in a popup first (it must open in this click
  // handler, before any await, or the browser blocks it), then the export runs.
  const saveToDrive = async () => {
    setError(null)
    if (drive.status?.available === false) {
      setError("Google Drive export isn't set up: the API has no OAuth client (agents/resume_builder/google_client.json).")
      return
    }
    if (!drive.status?.connected) {
      try {
        if (!(await drive.connect())) return
      } catch (e) {
        setError(errorMessage(e))
        return
      }
    }
    setExporting(true)
    try {
      const [file] = await exportDraftToDrive(draft.id, [tab])
      if (file) setDriveFiles((prev) => ({ ...prev, [driveKey]: file }))
      else setError("Nothing to save: this doc is empty.")
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        drive.markDisconnected()
        setError("The Google Drive sign-in expired. Click Save to Drive to sign in again.")
      } else setError(errorMessage(e))
    } finally {
      setExporting(false)
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
          {drive.connecting ? (
            <Button variant="ghost" size="sm" onClick={drive.cancelConnect}>
              <LoaderCircle className="animate-spin" />
              Waiting for Google… Cancel
            </Button>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={saveToDrive}
              disabled={drive.status === null || exporting || pending !== null}
              title={draftNumber ? `Saves Draft ${draftNumber} to Google Drive, in career_pilot_resume/${draft.position ?? ""}` : undefined}
            >
              {exporting ? <LoaderCircle className="animate-spin" /> : <CloudUpload />}
              {driveFile ? "Update Drive" : "Save to Drive"}
            </Button>
          )}
          {driveFile && (
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Open in Google Drive"
              nativeButton={false}
              render={<a href={driveFile.url} target="_blank" rel="noreferrer" />}
            >
              <ExternalLink />
            </Button>
          )}
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
