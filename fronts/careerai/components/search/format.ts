// Formatting helpers shared by the search page's tabs.
import type { Action } from "@/lib/api"

// Every application status of a job, in the order a job moves through them.
export const ACTIONS: Action[] = [
  "searched",
  "applied",
  "interview_scheduled",
  "interview_inprogress",
  "interview_done",
  "denied",
  "drop",
]

export function errorMessage(e: unknown) {
  return e instanceof Error ? e.message : String(e)
}

export function titleCase(value: string) {
  return value.replace(/[_-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

export function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" })
}

export function formatTime(value: string) {
  return new Date(value).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })
}
