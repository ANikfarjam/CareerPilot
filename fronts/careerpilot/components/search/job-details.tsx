"use client"

import { useEffect, useState } from "react"
import { Check, Minus, X } from "lucide-react"

import { Skeleton } from "@/components/ui/skeleton"
import { getJob, type Job } from "@/lib/api"
import { cn } from "@/lib/utils"

import { errorMessage } from "./format"

// Descriptions fetched so far (GET /jobs/{id}), so re-opening a row doesn't fetch again.
const descriptions = new Map<string, string | null>()

type Requirement = { skill: string; level: string }
type Status = "met" | "unmet" | "partial"

const STATUS_ICON = { met: Check, unmet: X, partial: Minus }
const STATUS_CLASS = { met: "text-brand-teal", unmet: "text-destructive", partial: "text-muted-foreground" }

// Case-insensitive, de-duplicated (the model sometimes lists the same gap twice).
const normalize = (s: string) => s.trim().toLowerCase()
const unique = (items: string[]) => [...new Map(items.map((s) => [normalize(s), s])).values()]

// Expanded row of the Results table: qualification_check's breakdown of the score
// (from the list response) and the job description (fetched on first open).
export function JobDetails({ job }: { job: Job }) {
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Qualifications job={job} />
      <Description jobId={job.id} />
    </div>
  )
}

// matched/missing are the model's own wording, usually but not always copied from a
// requirement; a requirement found in neither (e.g. split into a matched and a missing
// part) is shown as partly met, and the leftovers as other strengths and gaps.
function Qualifications({ job }: { job: Job }) {
  const matched = unique(job.matched ?? [])
  const missing = unique(job.missing ?? [])
  const requirements: Requirement[] = [
    ...new Map(
      (job.requirements ?? [])
        .map((r) => ({ skill: String(r.skill ?? ""), level: String(r.level ?? "required") }))
        .filter((r) => r.skill)
        .map((r) => [normalize(r.skill), r]),
    ).values(),
  ]
  const matchedSet = new Set(matched.map(normalize))
  const missingSet = new Set(missing.map(normalize))
  const skillSet = new Set(requirements.map((r) => normalize(r.skill)))
  const statusOf = (skill: string): Status =>
    matchedSet.has(normalize(skill)) ? "met" : missingSet.has(normalize(skill)) ? "unmet" : "partial"

  const required = requirements.filter((r) => r.level !== "preferred")
  const preferred = requirements.filter((r) => r.level === "preferred")
  const otherStrengths = matched.filter((s) => !skillSet.has(normalize(s)))
  const otherGaps = missing.filter((s) => !skillSet.has(normalize(s)))

  return (
    <section className="space-y-4">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Key qualifications</h3>
      {job.reasoning && <p className="text-sm leading-relaxed">{job.reasoning}</p>}
      <RequirementList title="Required" items={required} statusOf={statusOf} />
      <RequirementList title="Preferred" items={preferred} statusOf={statusOf} />
      <SkillChips title={requirements.length ? "Other strengths" : "Matched"} skills={otherStrengths} />
      <SkillChips title={requirements.length ? "Other gaps" : "Missing"} skills={otherGaps} />
      {!job.reasoning && requirements.length + matched.length + missing.length === 0 && (
        <p className="text-sm text-muted-foreground">No qualification breakdown for this job (saved before scoring details were stored).</p>
      )}
    </section>
  )
}

function RequirementList({ title, items, statusOf }: { title: string; items: Requirement[]; statusOf: (skill: string) => Status }) {
  if (items.length === 0) return null
  const statuses = items.map((r) => statusOf(r.skill))
  const met = statuses.filter((s) => s === "met").length
  const partial = statuses.filter((s) => s === "partial").length
  return (
    <div className="space-y-1.5">
      <p className="text-sm font-medium">
        {title}
        <span className="ml-2 text-xs font-normal text-muted-foreground">
          {met} of {items.length} met{partial > 0 && `, ${partial} partly`}
        </span>
      </p>
      <ul className="space-y-1">
        {items.map((r, i) => {
          const status = statuses[i]
          const Icon = STATUS_ICON[status]
          return (
            <li key={r.skill} className="flex items-start gap-2 text-sm">
              <Icon className={cn("mt-0.5 size-4 shrink-0", STATUS_CLASS[status])} aria-label={status === "partial" ? "partly met" : status} />
              <span className={cn(status !== "met" && "text-muted-foreground")}>{r.skill}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function SkillChips({ title, skills }: { title: string; skills: string[] }) {
  if (skills.length === 0) return null
  return (
    <div className="space-y-1.5">
      <p className="text-sm font-medium">{title}</p>
      <ul className="flex flex-wrap gap-1.5">
        {skills.map((skill) => (
          <li key={skill} className="rounded-md border border-brand-blue/30 bg-brand-blue/10 px-2 py-0.5 text-xs font-medium">
            {skill}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Description({ jobId }: { jobId: string }) {
  const [description, setDescription] = useState<string | null | undefined>(() => descriptions.get(jobId))
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (descriptions.has(jobId)) return
    let stale = false
    getJob(jobId)
      .then((job) => {
        descriptions.set(jobId, job.description)
        if (!stale) setDescription(job.description)
      })
      .catch((e) => !stale && setError(errorMessage(e)))
    return () => {
      stale = true
    }
  }, [jobId])

  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Description</h3>
      {error ? (
        <p className="text-sm text-destructive">{error}</p>
      ) : description === undefined ? (
        <div className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-4/5" />
        </div>
      ) : description ? (
        <div className="max-h-96 overflow-y-auto rounded-md border bg-background p-3 text-sm leading-relaxed whitespace-pre-line">
          {description}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No description saved.</p>
      )}
    </section>
  )
}
