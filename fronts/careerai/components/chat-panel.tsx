"use client"

import { useEffect, useRef, useState } from "react"
import { Bot, LoaderCircle, MessagesSquare, SendHorizontal, TriangleAlert, WifiOff } from "lucide-react"

import { Markdown } from "@/components/markdown"
import { Button } from "@/components/ui/button"
import type { PendingReply, SocketState } from "@/hooks/use-resume-chat"
import type { ChatMessage } from "@/lib/api"
import { cn } from "@/lib/utils"

const SUGGESTIONS = [
  "Make the summary shorter and punchier",
  "Add my StockMarket project",
  "Emphasize my Kubernetes and MLOps work",
  "Which skills from the posting am I missing?",
]

type ChatPanelProps = {
  messages: ChatMessage[]
  pending: PendingReply | null
  socketState: SocketState
  error: string | null
  onSend: (content: string) => boolean
  className?: string
}

// Chat with the resume editor (resume builder page): saved messages, the reply being streamed,
// and an input that sends on Enter (Shift+Enter for a new line).
export function ChatPanel({ messages, pending, socketState, error, onSend, className }: ChatPanelProps) {
  const [input, setInput] = useState("")
  const scroller = useRef<HTMLDivElement>(null)
  const canSend = socketState === "open" && !pending

  // Follow the conversation as it grows and while the reply streams in.
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" })
  }, [messages.length, pending?.chat, pending?.phase])

  const submit = (content: string) => {
    if (onSend(content)) setInput("")
  }

  return (
    <section className={cn("flex min-h-0 flex-col rounded-2xl border bg-card", className)}>
      <header className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <MessagesSquare className="size-4 text-brand-teal" />
          Resume assistant
        </div>
        <ConnectionBadge state={socketState} />
      </header>

      <div ref={scroller} className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 && !pending && (
          <div className="space-y-3 py-6 text-center">
            <Bot className="mx-auto size-6 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              Ask for a change and the resume or side projects update as the reply streams in.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  disabled={!canSend}
                  onClick={() => submit(s)}
                  className="rounded-full border px-3 py-1 text-xs text-muted-foreground transition hover:border-brand-teal/40 hover:text-foreground disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <Bubble key={`${m.at}-${i}`} role={m.role}>
            {m.content}
          </Bubble>
        ))}

        {pending && (
          <>
            <Bubble role="user">{pending.message}</Bubble>
            {pending.chat.trim() ? (
              <Bubble role="assistant">{pending.chat}</Bubble>
            ) : (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <LoaderCircle className="size-3.5 animate-spin" />
                {pending.phase === "thinking" ? "Thinking…" : "Writing…"}
              </div>
            )}
            {(pending.resume !== null || pending.side_projects !== null) && (
              <p className="flex items-center gap-2 text-xs text-brand-teal">
                <LoaderCircle className="size-3.5 animate-spin" />
                Rewriting {pending.resume !== null ? "the resume" : "the side projects"}…
              </p>
            )}
          </>
        )}
      </div>

      {error && (
        <p className="mx-4 mb-2 flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          <TriangleAlert className="mt-px size-3.5 shrink-0" />
          {error}
        </p>
      )}

      <form
        className="flex items-end gap-2 border-t p-3"
        onSubmit={(e) => {
          e.preventDefault()
          submit(input)
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault()
              submit(input)
            }
          }}
          rows={2}
          placeholder={socketState === "open" ? "Ask for a change…" : "Connecting…"}
          aria-label="Message the resume assistant"
          className="max-h-40 min-h-10 flex-1 resize-none rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
        />
        <Button type="submit" size="icon" disabled={!canSend || !input.trim()} aria-label="Send">
          {pending ? <LoaderCircle className="animate-spin" /> : <SendHorizontal />}
        </Button>
      </form>
    </section>
  )
}

function Bubble({ role, children }: { role: ChatMessage["role"]; children: string }) {
  const isUser = role === "user"
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed",
          isUser ? "rounded-br-sm bg-brand-teal/15 text-foreground" : "rounded-bl-sm bg-muted",
        )}
      >
        {isUser ? <p className="whitespace-pre-wrap">{children}</p> : <Markdown>{children.trim()}</Markdown>}
      </div>
    </div>
  )
}

function ConnectionBadge({ state }: { state: SocketState }) {
  if (state === "open") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-brand-green">
        <span className="size-1.5 rounded-full bg-brand-green" />
        Live
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      {state === "connecting" ? <LoaderCircle className="size-3 animate-spin" /> : <WifiOff className="size-3" />}
      {state === "connecting" ? "Connecting" : "Offline"}
    </span>
  )
}
