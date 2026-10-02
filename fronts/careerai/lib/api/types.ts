// Types of the CareerAI API. Every request/response type is generated from apis/schemas.py
// (lib/client/types.gen.ts, `just gen-api`); this file only renames a few for the UI and
// adds the resume chat websocket's events, which OpenAPI can't describe.
import type { AgentRunRequest, JobOut, ResumeDraftOut, ResumeDraftUpdate, SideProject } from "@/lib/client"

export type {
  Action,
  ActionRow,
  AgentRun,
  AgentRunRequest,
  AgentRunSummary,
  AnalyticsReport,
  AnalyticsRun,
  AnalyticsTables,
  ChatMessage,
  CompanyRow,
  CompatibilityRow,
  DraftVersion,
  FunnelRow,
  JobOut,
  JobPage,
  JobType,
  JobTypeRow,
  ListJobsData,
  NearMissJob,
  ResumeDraftOut,
  ResumeDraftSummary,
  ResumeDraftUpdate,
  ResumeReport,
  RunStatus,
  SideProject,
  SkillGap,
  WeeklyRow,
} from "@/lib/client"

export type Job = JobOut
export type ResumeDraft = ResumeDraftOut // versions are oldest first; index is revertDraft's version
export type Sandbox = NonNullable<AgentRunRequest["sandbox"]>
export type Effort = SideProject["effort"]
export type DocTarget = keyof ResumeDraftUpdate // "resume" | "side_projects"

// Events of WS /agents/resume/drafts/{draft_id}/chat, server -> client
// (apis/reposetories/agents.py resume_chat).
export type ChatEvent =
  | { type: "status"; state: "thinking" | "writing" }
  | { type: "token"; target: "chat" | DocTarget; text: string }
  | { type: "done"; draft: ResumeDraft }
  | { type: "error"; detail: string }
