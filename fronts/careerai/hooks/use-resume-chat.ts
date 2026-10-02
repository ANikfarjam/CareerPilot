import { useCallback, useEffect, useRef, useState } from "react"

import { chatSocketUrl, type ChatEvent, type DocTarget, type ResumeDraft } from "@/lib/api"

export type SocketState = "connecting" | "open" | "closed"

// The reply being streamed: the user's message and what the bot has written so far.
// A doc is null until the bot starts rewriting it.
export type PendingReply = {
  message: string
  phase: "thinking" | "writing"
  chat: string
  resume: string | null
  side_projects: string | null
}

const MAX_BACKOFF_MS = 15000

// Chat with the resume editor over WS /agents/resume/drafts/{draftId}/chat (apis/reposetories/agents.py).
// Streams the reply into `pending`; when it is saved, calls onDraft with the updated draft.
// Reconnects with backoff unless the draft doesn't exist (close code 4404).
export function useResumeChat(draftId: string | null, onDraft: (draft: ResumeDraft) => void) {
  const [socketState, setSocketState] = useState<SocketState>("closed")
  const [pending, setPending] = useState<PendingReply | null>(null)
  const [error, setError] = useState<string | null>(null)
  const socket = useRef<WebSocket | null>(null)
  const streaming = useRef(false) // a reply is in flight; mirrors pending !== null for the socket handlers
  const onDraftRef = useRef(onDraft)

  useEffect(() => {
    onDraftRef.current = onDraft
  }, [onDraft])

  useEffect(() => {
    if (!draftId) return
    let disposed = false
    let attempt = 0
    let retry: ReturnType<typeof setTimeout> | undefined

    const handle = (event: ChatEvent) => {
      switch (event.type) {
        case "status":
          setPending((p) => p && { ...p, phase: event.state })
          break
        case "token":
          setPending((p) => {
            if (!p) return p
            if (event.target === "chat") return { ...p, chat: p.chat + event.text }
            return { ...p, [event.target]: (p[event.target as DocTarget] ?? "") + event.text }
          })
          break
        case "done":
          streaming.current = false
          setPending(null)
          onDraftRef.current(event.draft)
          break
        case "error":
          streaming.current = false
          setPending(null)
          setError(event.detail)
          break
      }
    }

    const connect = () => {
      setSocketState("connecting")
      const ws = new WebSocket(chatSocketUrl(draftId))
      socket.current = ws
      ws.onopen = () => {
        attempt = 0
        setSocketState("open")
        setError(null)
      }
      ws.onmessage = (msg) => handle(JSON.parse(msg.data) as ChatEvent)
      ws.onclose = (e) => {
        if (socket.current === ws) socket.current = null
        if (disposed) return
        setSocketState("closed")
        if (streaming.current) setError("Connection lost before the reply finished.")
        streaming.current = false
        setPending(null)
        if (e.code === 4404) {
          setError("This draft no longer exists.")
          return
        }
        retry = setTimeout(connect, Math.min(1000 * 2 ** attempt++, MAX_BACKOFF_MS))
      }
    }

    connect()
    return () => {
      disposed = true
      clearTimeout(retry)
      socket.current?.close()
      socket.current = null
      streaming.current = false
      setPending(null)
      setSocketState("closed")
    }
  }, [draftId])

  // Sends one message; false if the socket isn't open or a reply is still streaming.
  const send = useCallback(
    (content: string) => {
      const ws = socket.current
      const message = content.trim()
      if (!message || streaming.current || !ws || ws.readyState !== WebSocket.OPEN) return false
      streaming.current = true
      setError(null)
      setPending({ message, phase: "thinking", chat: "", resume: null, side_projects: null })
      ws.send(JSON.stringify({ type: "message", content: message }))
      return true
    },
    [],
  )

  return { socketState, pending, error, send }
}
