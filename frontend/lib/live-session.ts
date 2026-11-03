'use client'

import { useEffect, useState } from 'react'

export type LiveClaim = {
  id: string
  section: string
  label: string
  text: string
  source?: string
  rationale?: string
  flags?: string[]
  confidenceScore?: number
}

export type LiveTurn = {
  speaker: string
  speakerInitials: string
  speakerName: string
  timestamp: string
  text: string
}

export type LiveSessionPayload = {
  patient: {
    id: string
    name: string
    age?: number | null
    sex?: string | null
    mrn: string
    initials: string
    lastSession?: string
    totalSessions?: number
    unsupportedRate?: number
  }
  session: {
    id: string
    doctorName: string
    doctorInitials?: string
    time: string
    source: string
    status: string
    riskLevel: string
    specialty?: string
    consultationType?: string
    transcriptModel?: string
    duration?: string
    transcriptStatus?: string
    totalClaims: number
    retentionRate: number
    unsupportedPercentage: number
  }
  transcript: { turns: LiveTurn[] }
  claims: LiveClaim[]
  soapNote: {
    original: Record<string, string>
    filtered: Record<string, string>
  }
  workspace?: {
    claimsVerified: number
    unsupportedRate: number
    retentionRate: number
    verdictShares: Record<string, number>
  }
  formattedNote?: string
}

export type LiveEnvelope = {
  status: 'waiting' | 'ready' | string
  updatedAt?: number
  message?: string
  session?: LiveSessionPayload | null
}

export function useLiveSession(pollMs = 2500) {
  const [envelope, setEnvelope] = useState<LiveEnvelope | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const res = await fetch(`/live-session.json?t=${Date.now()}`, { cache: 'no-store' })
        if (!res.ok) return
        const data = (await res.json()) as LiveEnvelope
        if (!cancelled) setEnvelope(data)
      } catch {
        /* UI falls back to demo data */
      }
    }
    load()
    const id = window.setInterval(load, pollMs)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [pollMs])

  return envelope
}
