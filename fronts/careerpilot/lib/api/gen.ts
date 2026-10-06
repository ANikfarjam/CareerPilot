// One typed function per CareerPilot API request. Each wraps the generated SDK
// (lib/client/sdk.gen.ts), which sends it through the shared client in
// lib/client/client.gen.ts; failed requests throw ApiError.
import * as sdk from "@/lib/client"
import type { Action, AgentRunRequest, KnowledgeRunRequest, ListJobsData, ResumeDraftUpdate } from "@/lib/client"
import { API_URL } from "@/lib/hey-api"

import type { Sandbox } from "./types"

export class ApiError extends Error {
  constructor(
    public status: number, // 0 when the API couldn't be reached
    message: string,
  ) {
    super(message)
  }
}

// The data of an SDK call, or an ApiError with FastAPI's `detail` (a string, or the
// validation errors of a 422).
async function unwrap<T>(call: Promise<{ data?: T; error?: unknown; response?: Response }>): Promise<T> {
  const { data, error, response } = await call
  if (response?.ok) return data as T
  const detail = (error as { detail?: unknown } | undefined)?.detail
  const message =
    typeof detail === "string"
      ? detail
      : detail !== undefined
        ? JSON.stringify(detail)
        : response
          ? `${response.status} ${response.statusText}`
          : `Could not reach the API at ${API_URL}`
  throw new ApiError(response?.status ?? 0, message)
}

// ─────────────────────────────────────────────────────────
// Agent runs: portal_search -> qualification_check -> db_ingestion
// ─────────────────────────────────────────────────────────

// Starts a job search (plus any manual_positions, scored and saved by the same run);
// 409 while another agent run is in progress.
export const startRun = (body: AgentRunRequest = {}) => unwrap(sdk.startRun({ body }))

export const listRuns = () => unwrap(sdk.listRuns())

export const getRun = (runId: string) => unwrap(sdk.getRun({ path: { run_id: runId } }))

// Portal names from portals.yml, for AgentRunRequest.portals.
export const listPortals = () => unwrap(sdk.listPortals())

// Positive title_filter keywords from portals.yml: the positions the search targets.
export const listTargetPositions = () => unwrap(sdk.listTargetPositions())

// Edit portals.yml; each returns the updated list. 409 while an agent run is in progress.
export const addPortal = (name: string, careersUrl: string) =>
  unwrap(sdk.addPortal({ body: { name, careers_url: careersUrl } }))

// The portal stays in portals.yml with enabled: false.
export const removePortal = (name: string) => unwrap(sdk.removePortal({ path: { name } }))

export const addTargetPosition = (keyword: string) => unwrap(sdk.addTargetPosition({ body: { keyword } }))

// 422 if it is the last target position.
export const removeTargetPosition = (keyword: string) =>
  unwrap(sdk.removeTargetPosition({ path: { keyword } }))

// ─────────────────────────────────────────────────────────
// Analytics
// ─────────────────────────────────────────────────────────

// Chart tables only (fast, no LLM).
export const getAnalytics = () => unwrap(sdk.getAnalytics())

// Starts the analytics agent; 409 while another agent run is in progress.
export const startAnalyticsRun = (sandbox: Sandbox = "sandbox-cpu") =>
  unwrap(sdk.startAnalyticsRun({ body: { sandbox } }))

export const getAnalyticsRun = (runId: string) => unwrap(sdk.getAnalyticsRun({ path: { run_id: runId } }))

// ─────────────────────────────────────────────────────────
// Knowledge base (agents/knowledge_base)
// ─────────────────────────────────────────────────────────

// The Docs/user_docs folders, what each holds (as a tree) and the current knowledge base.
export const getUserDocs = () => unwrap(sdk.getUserDocs())

// Creates the missing Docs/user_docs folders; returns the updated listing.
export const createUserDocsFolders = () => unwrap(sdk.createUserDocsFolders())

// Rebuilds the knowledge base from the chosen kinds and tunes portals.yml; takes several minutes.
// 422 if the chosen folders are empty, 409 while another agent run is in progress.
export const startKnowledgeRun = (body: KnowledgeRunRequest = {}) => unwrap(sdk.startKnowledgeRun({ body }))

export const listKnowledgeRuns = () => unwrap(sdk.listKnowledgeRuns())

export const getKnowledgeRun = (runId: string) => unwrap(sdk.getKnowledgeRun({ path: { run_id: runId } }))

// ─────────────────────────────────────────────────────────
// Job board (apis/reposetories/jobs.py)
// ─────────────────────────────────────────────────────────

export const listJobs = (query: ListJobsData["query"] = {}) => unwrap(sdk.listJobs({ query }))

export const getJob = (jobId: string) => unwrap(sdk.getJob({ path: { job_id: jobId } }))

export const updateJobAction = (jobId: string, action: Action) =>
  unwrap(sdk.updateJobAction({ path: { job_id: jobId }, body: { action } }))

// ─────────────────────────────────────────────────────────
// Resume builder + chat (agents/resume_builder)
// ─────────────────────────────────────────────────────────

// Builds a resume for a saved job and saves it as a new draft; takes a minute or two.
// 409 while another agent run is using the model.
export const buildResume = (jobId: string) => unwrap(sdk.buildResume({ path: { job_id: jobId } }))

export const listDrafts = (jobId?: string) => unwrap(sdk.listResumeDrafts({ query: { job_id: jobId } }))

export const getDraft = (draftId: string) => unwrap(sdk.getResumeDraft({ path: { draft_id: draftId } }))

// Manual edit; fields left out are not changed.
export const updateDraft = (draftId: string, body: ResumeDraftUpdate) =>
  unwrap(sdk.updateResumeDraft({ path: { draft_id: draftId }, body }))

export const revertDraft = (draftId: string, version: number) =>
  unwrap(sdk.revertResumeDraft({ path: { draft_id: draftId, version } }))

// ws(s):// URL of a draft's chat, on the same host as API_URL (OpenAPI has no websockets,
// so this one isn't generated; its events are ChatEvent).
export const chatSocketUrl = (draftId: string) =>
  `${API_URL.replace(/^http/, "ws")}/agents/resume/drafts/${draftId}/chat`

export const health = () => unwrap(sdk.health())
