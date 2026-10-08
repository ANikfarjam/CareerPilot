"use client"

import Link from "next/link"
import { ExternalLink, FileText, Search, Sparkles } from "lucide-react"

import { ACTIONS, formatDate, titleCase } from "@/components/search/format"
import { MatchScore } from "@/components/search/match-score"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { Action, Job } from "@/lib/api"
import { cn } from "@/lib/utils"

const ACTION_ITEMS = Object.fromEntries(ACTIONS.map((a) => [a, titleCase(a)]))

type JobsTableProps = {
  jobs: Job[] | null // null while loading
  filter: string
  onFilter: (value: string) => void
  selectedId: string | null
  draftCounts: Record<string, number> | null // job id -> number of resume drafts
  onOpen: (job: Job) => void
  onBuild: (job: Job) => void // only offered while the job has no draft
  building: boolean
  onAction: (job: Job, action: Action) => void
}

// Resume builder's Jobs tab: the saved jobs with their editable status and draft count.
// Clicking a row opens the job in the Editor tab; Build starts a job's first draft.
export function JobsTable({ jobs, filter, onFilter, selectedId, draftCounts, onOpen, onBuild, building, onAction }: JobsTableProps) {
  return (
    <div className="space-y-4">
      <div className="relative sm:w-72">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={filter}
          onChange={(e) => onFilter(e.target.value)}
          placeholder="Filter company or position"
          aria-label="Filter jobs"
          className="pl-8"
        />
      </div>

      <div className="overflow-hidden rounded-xl border bg-card">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-4">Company</TableHead>
              <TableHead>Position</TableHead>
              <TableHead>Match</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Drafts</TableHead>
              <TableHead>Updated</TableHead>
              <TableHead className="pr-4 text-right">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {jobs === null
              ? [0, 1, 2, 3].map((i) => (
                  <TableRow key={i} className="hover:bg-transparent">
                    <TableCell colSpan={7} className="px-4">
                      <Skeleton className="h-8 w-full" />
                    </TableCell>
                  </TableRow>
                ))
              : jobs.map((job) => {
                  const drafts = draftCounts?.[job.id] ?? 0
                  return (
                    <TableRow
                      key={job.id}
                      onClick={() => onOpen(job)}
                      data-state={job.id === selectedId ? "selected" : undefined}
                      className={cn("cursor-pointer", job.id === selectedId && "bg-brand-teal/10 hover:bg-brand-teal/15")}
                    >
                      <TableCell className="pl-4 font-medium">{job.company_name}</TableCell>
                      <TableCell className="max-w-80 whitespace-normal">{job.position}</TableCell>
                      <TableCell>
                        <MatchScore score={job.compatibility} />
                      </TableCell>
                      {/* The status select must not open the row */}
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <Select
                          items={ACTION_ITEMS}
                          value={job.action}
                          onValueChange={(v) => v && v !== job.action && onAction(job, v as Action)}
                        >
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
                      <TableCell className="tabular-nums text-muted-foreground">
                        {draftCounts === null ? "…" : drafts}
                      </TableCell>
                      <TableCell className="text-muted-foreground">{formatDate(job.update_at)}</TableCell>
                      <TableCell className="pr-4 text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-1">
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
                          {drafts ? (
                            <Button variant="outline" size="sm" onClick={() => onOpen(job)}>
                              <FileText />
                              Open
                            </Button>
                          ) : (
                            <Button variant="secondary" size="sm" onClick={() => onBuild(job)} disabled={building}>
                              <Sparkles />
                              Build
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
          </TableBody>
          {jobs?.length === 0 && (
            <TableCaption className="mt-0 border-t py-12">
              {filter ? (
                "No job matches."
              ) : (
                <span className="inline-flex flex-col items-center gap-3">
                  No saved jobs yet.
                  <Button variant="outline" size="sm" nativeButton={false} render={<Link href="/search/page" />}>
                    Go to search
                  </Button>
                </span>
              )}
            </TableCaption>
          )}
        </Table>
      </div>
    </div>
  )
}
