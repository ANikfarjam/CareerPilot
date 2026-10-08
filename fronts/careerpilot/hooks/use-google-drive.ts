"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import { disconnectDrive, driveLoginUrl, getDriveStatus, type DriveStatus } from "@/lib/api"

const POLL_MS = 1500
const CONNECT_TIMEOUT_MS = 5 * 60_000

// The Google Drive connection used to export resumes. connect() opens Google's sign-in in a
// popup and resolves true once the API reports the account connected. Google's pages cut the
// popup off from this window (Cross-Origin-Opener-Policy), so we poll GET /drive/status instead
// of listening to the popup. Call connect() straight from a click, or the popup is blocked.
export function useGoogleDrive() {
  const [status, setStatus] = useState<DriveStatus | null>(null) // null while loading
  const [connecting, setConnecting] = useState(false)
  const cancelRef = useRef<(() => void) | null>(null)

  const refresh = useCallback(async () => {
    try {
      const next = await getDriveStatus()
      setStatus(next)
      return next
    } catch {
      setStatus({ available: false, connected: false, email: null })
      return null
    }
  }, [])

  // Also re-check on focus: the chat's "Connect Google Drive" link signs in from another tab.
  useEffect(() => {
    getDriveStatus()
      .then(setStatus)
      .catch(() => setStatus({ available: false, connected: false, email: null }))
    const onFocus = () => refresh()
    window.addEventListener("focus", onFocus)
    return () => {
      window.removeEventListener("focus", onFocus)
      cancelRef.current?.()
    }
  }, [refresh])

  const connect = useCallback((): Promise<boolean> => {
    const popup = window.open(driveLoginUrl(), "careerpilot-drive", "popup,width=520,height=680")
    if (!popup) return Promise.reject(new Error("Your browser blocked the Google sign-in window; allow popups for this page."))
    setConnecting(true)
    return new Promise<boolean>((resolve) => {
      const started = Date.now()
      let timer: ReturnType<typeof setTimeout>
      const finish = (ok: boolean) => {
        clearTimeout(timer)
        cancelRef.current = null
        setConnecting(false)
        resolve(ok)
      }
      cancelRef.current = () => finish(false)
      const poll = async () => {
        const next = await refresh()
        if (cancelRef.current === null) return // cancelled meanwhile
        if (next?.connected) finish(true)
        else if (Date.now() - started > CONNECT_TIMEOUT_MS) finish(false)
        else timer = setTimeout(poll, POLL_MS)
      }
      timer = setTimeout(poll, POLL_MS)
    })
  }, [refresh])

  // Stops waiting for a sign-in the user abandoned (e.g. closed the popup).
  const cancelConnect = useCallback(() => cancelRef.current?.(), [])

  const disconnect = useCallback(async () => {
    setStatus(await disconnectDrive())
  }, [])

  // The API said the sign-in is gone (a 401 from an export): show the connect state again.
  const markDisconnected = useCallback(
    () => setStatus((s) => s && { ...s, connected: false, email: null }),
    [],
  )

  return { status, connecting, connect, cancelConnect, disconnect, markDisconnected, refresh }
}

export type GoogleDrive = ReturnType<typeof useGoogleDrive>
