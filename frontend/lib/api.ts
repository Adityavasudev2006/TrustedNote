import type { LiveSessionPayload } from '@/lib/live-session'

export type SessionListRow = {
  id: string
  patient: string
  doctor: string
  time: string
  source: string
  status: string
  risk: string
  claims: number
  rate: number
}

const API = typeof window !== 'undefined' ? '' : 'http://127.0.0.1:8765'

async function parseJsonResponse(res: Response): Promise<Record<string, unknown>> {
  const text = await res.text()
  try {
    return JSON.parse(text) as Record<string, unknown>
  } catch {
    const snippet = text.slice(0, 120).replace(/\s+/g, ' ')
    throw new Error(
      res.ok
        ? `Invalid server response: ${snippet}`
        : `Server error (${res.status}): ${snippet || res.statusText}. Keep python main.py running.`,
    )
  }
}

export async function fetchSessionList(): Promise<SessionListRow[]> {
  const res = await fetch(`${API}/api/sessions`, { cache: 'no-store' })
  if (!res.ok) return []
  const data = await parseJsonResponse(res)
  return (data.sessions as SessionListRow[]) ?? []
}

export async function fetchSessionById(id: string): Promise<LiveSessionPayload | null> {
  const res = await fetch(`${API}/api/sessions/${encodeURIComponent(id)}`, { cache: 'no-store' })
  if (!res.ok) return null
  const data = await parseJsonResponse(res)
  return (data.session as LiveSessionPayload) ?? null
}

export type SessionJobStatus = {
  status: 'processing' | 'complete' | 'error'
  sessionId: string
  error?: string
  listRow?: SessionListRow
}

export async function fetchSessionJobStatus(sessionId: string): Promise<SessionJobStatus> {
  const res = await fetch(`${API}/api/sessions/${encodeURIComponent(sessionId)}/status`, {
    cache: 'no-store',
  })
  const data = await parseJsonResponse(res)
  if (!res.ok) {
    throw new Error(String(data.error || 'Could not read job status'))
  }
  return data as SessionJobStatus
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export type GenerateSessionInput = {
  transcript: string
  patientName: string
  doctorName?: string
  age?: number | string
  sex?: string
  mrn?: string
  specialty?: string
  consultationType?: string
}

export async function transcribeAudio(blob: Blob, filename = 'recording.webm'): Promise<{ text: string; engine: string }> {
  const form = new FormData()
  form.append('audio', blob, filename)
  const res = await fetch(`${API}/api/transcribe`, {
    method: 'POST',
    body: form,
  })
  const data = await parseJsonResponse(res)
  if (!res.ok) {
    throw new Error(String(data.error || 'Transcription failed'))
  }
  return { text: String(data.text || ''), engine: String(data.engine || 'whisper') }
}

export async function generateSession(input: GenerateSessionInput): Promise<{
  sessionId: string
  session: LiveSessionPayload
  listRow?: SessionListRow
}> {
  const res = await fetch(`${API}/api/sessions/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  const data = await parseJsonResponse(res)
  if (!res.ok && res.status !== 202) {
    throw new Error(String(data.error || 'Generation failed. Is python main.py running?'))
  }

  const sessionId = String(data.sessionId || '')
  if (!sessionId) {
    throw new Error('Server did not return a session id')
  }

  const deadline = Date.now() + 45 * 60 * 1000
  while (Date.now() < deadline) {
    const job = await fetchSessionJobStatus(sessionId)
    if (job.status === 'error') {
      throw new Error(job.error || 'Pipeline failed')
    }
    if (job.status === 'complete') {
      const session = await fetchSessionById(sessionId)
      if (!session) {
        throw new Error('Session finished but could not be loaded')
      }
      return { sessionId, session, listRow: job.listRow }
    }
    await sleep(2500)
  }

  throw new Error('Generation timed out. Check the terminal — results may still appear when complete.')
}
