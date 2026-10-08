"use client"

import { Fragment, useEffect, useState } from "react"
import { ArrowDown, ArrowUp, ChevronRight, ExternalLink, Search } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { listJobs, updateJobAction, type Action, type Job } from "@/lib/api"
import { cn } from "@/lib/utils"

import { ACTIONS, errorMessage, formatDate, titleCase } from "./format"
import { JobDetails } from "./job-details"
import { MatchScore } from "./match-score"

type SortBy = "update_at" | "compatibility" | "company_name"

const ACTION_ITEMS = Object.fromEntries(ACTIONS.map((a) => [a, titleCase(a)]))
const FILTER_ITEMS = { all: "All statuses", ...ACTION_ITEMS }

// Results tab: the saved (qualified) jobs, searchable and sortable, with an editable status.
// Each row expands to show its key qualifications and description.
// refreshKey changes when a run saves new jobs; onTotal reports the unfiltered count.
export function ResultsTab({ refreshKey, onTotal }: { refreshKey: string; onTotal: (total: number) => void }) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [query, setQuery] = useState("") // search, debounced
  const [action, setAction] = useState<Action | "all">("all")
  const [sortBy, setSortBy] = useState<SortBy>("update_at")
  const [order, setOrder] = useState<"asc" | "desc">("desc")
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 300)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    let stale = false
    listJobs({
      search: query || undefined,
      action: action === "all" ? undefined : action,
      sort_by: sortBy,
      order,
      limit: 200,
    })
      .then((page) => {
        if (stale) return
        setJobs(page.items)
        setTotal(page.total)
        setError(null)
        if (!query && action === "all") onTotal(page.total)
      })
      .catch((e) => !stale && setError(errorMessage(e)))
      .finally(() => !stale && setLoading(false))
    return () => {
      stale = true
    }
  }, [query, action, sortBy, order, refreshKey, onTotal])

  // Optimistic: show the new status right away, put the old one back if the API refuses.
  const changeAction = async (job: Job, next: Action) => {
    const setJobAction = (value: Action) =>
      setJobs((list) => list.map((j) => (j.id === job.id ? { ...j, action: value } : j)))
    setJobAction(next)
    try {
      await updateJobAction(job.id, next)
    } catch (e) {
      setJobAction(job.action)
      setError(errorMessage(e))
    }
  }

  const toggle = (id: string) =>
    setExpanded((open) => {
      const next = new Set(open)
      if (!next.delete(id)) next.add(id)
      return next
    })

  const sortOn = (column: SortBy) => {
    if (sortBy === column) setOrder((o) => (o === "asc" ? "desc" : "asc"))
    else {
      setSortBy(column)
      setOrder(column === "company_name" ? "asc" : "desc")
    }
  }

  const scored = jobs.length ? jobs.reduce((sum, j) => sum + j.compatibility, 0) / jobs.length : null

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative sm:w-72">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search company or position" className="pl-8" />
        </div>
        <Select items={FILTER_ITEMS} value={action} onValueChange={(v) => v && setAction(v as Action | "all")}>
          <SelectTrigger className="sm:w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {ACTIONS.map((a) => (
              <SelectItem key={a} value={a}>
                {titleCase(a)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-sm text-muted-foreground sm:ml-auto">
          {total} job{total === 1 ? "" : "s"}
          {scored !== null && ` · avg match ${scored.toFixed(1)}/10`}
        </p>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="overflow-hidden rounded-xl border bg-card">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-8 pl-3">
                <span className="sr-only">Details</span>
              </TableHead>
              <SortHead label="Company" column="company_name" sortBy={sortBy} order={order} onSort={sortOn} />
              <TableHead>Position</TableHead>
              <TableHead>Type</TableHead>
              <SortHead label="Match" column="compatibility" sortBy={sortBy} order={order} onSort={sortOn} />
              <TableHead>Status</TableHead>
              <SortHead label="Updated" column="update_at" sortBy={sortBy} order={order} onSort={sortOn} />
              <TableHead className="pr-4 text-right">
                <span className="sr-only">Link</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {jobs.map((job) => {
              const open = expanded.has(job.id)
              return (
                <Fragment key={job.id}>
                  <TableRow>
                    <TableCell className="pl-3">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={open ? "Hide details" : "Show details"}
                        aria-expanded={open}
                        aria-controls={`job-details-${job.id}`}
                        onClick={() => toggle(job.id)}
                      >
                        <ChevronRight className={cn("transition-transform", open && "rotate-90")} />
                      </Button>
                    </TableCell>
                    <TableCell className="cursor-pointer font-medium" onClick={() => toggle(job.id)}>
                      {job.company_name}
                    </TableCell>
                    <TableCell className="max-w-80 cursor-pointer whitespace-normal" onClick={() => toggle(job.id)}>
                      {job.position}
                      {job.post_id && <span className="ml-1.5 text-xs text-muted-foreground">#{job.post_id}</span>}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{titleCase(job.job_type)}</TableCell>
                    <TableCell>
                      <MatchScore score={job.compatibility} />
                    </TableCell>
                    <TableCell>
                      <Select items={ACTION_ITEMS} value={job.action} onValueChange={(v) => v && v !== job.action && changeAction(job, v as Action)}>
                        <SelectTrigger size="sm" className="w-44" aria-label={`Status of ${job.position}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {ACTIONS.map((a) => (
                            <SelectItem key={a} value={a}>
                              {titleCase(a)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{formatDate(job.update_at)}</TableCell>
                    <TableCell className="pr-4 text-right">
                      {job.link && (
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label="Open posting"
                          nativeButton={false}
                          render={<a href={job.link} target="_blank" rel="noopener noreferrer" />}
                        >
                          <ExternalLink />
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                  {open && (
                    <TableRow id={`job-details-${job.id}`} className="hover:bg-transparent">
                      <TableCell colSpan={8} className="bg-muted/30 p-4 whitespace-normal">
                        <JobDetails job={job} />
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              )
            })}
          </TableBody>
          {jobs.length === 0 && (
            <TableCaption className="mt-0 border-t py-16">
              {loading
                ? "Loading…"
                : query || action !== "all"
                  ? "No jobs match these filters."
                  : "No results yet. Run a search to get started."}
            </TableCaption>
          )}
        </Table>
      </div>
    </div>
  )
}

type SortHeadProps = {
  label: string
  column: SortBy
  sortBy: SortBy
  order: "asc" | "desc"
  onSort: (column: SortBy) => void
  className?: string
}

function SortHead({ label, column, sortBy, order, onSort, className }: SortHeadProps) {
  const active = sortBy === column
  const Arrow = order === "asc" ? ArrowUp : ArrowDown
  return (
    <TableHead className={className} aria-sort={active ? (order === "asc" ? "ascending" : "descending") : undefined}>
      <button
        type="button"
        onClick={() => onSort(column)}
        className={cn("inline-flex items-center gap-1 hover:text-foreground", !active && "text-muted-foreground")}
      >
        {label}
        <Arrow className={cn("size-3.5", !active && "opacity-0")} />
      </button>
    </TableHead>
  )
}
