'use client'

import { Mic, Square, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { generateSession, transcribeAudio, type SessionListRow } from '@/lib/api'
import type { LiveSessionPayload } from '@/lib/live-session'

type Props = {
  open: boolean
  onClose: () => void
  onGenerated: (sessionId: string, session: LiveSessionPayload, row?: SessionListRow) => void
}

function pickRecorderMime(): string {
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']
  for (const t of types) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(t)) return t
  }
  return ''
}

export function NewSessionModal({ open, onClose, onGenerated }: Props) {
  const [transcript, setTranscript] = useState('')
  const [patientName, setPatientName] = useState('')
  const [doctorName, setDoctorName] = useState('Maya Chen')
  const [age, setAge] = useState('')
  const [sex, setSex] = useState('U')
  const [mrn, setMrn] = useState('')
  const [consultationType, setConsultationType] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [recording, setRecording] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [recordSeconds, setRecordSeconds] = useState(0)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    if (!open) {
      stopRecordingSilently()
    }
    return () => stopRecordingSilently()
  }, [open])

  function stopRecordingSilently() {
    if (timerRef.current) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.stop()
      } catch {
        /* already stopped */
      }
    }
    mediaRecorderRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    setRecording(false)
    setRecordSeconds(0)
  }

  async function startRecording() {
    setError(null)
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setError('Microphone access is not available in this browser.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const mime = pickRecorderMime()
      const recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream)
      chunksRef.current = []
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorder.onstop = () => {
        void finishRecording(recorder.mimeType || mime || 'audio/webm')
      }
      recorder.start(1000)
      mediaRecorderRef.current = recorder
      setRecording(true)
      setRecordSeconds(0)
      timerRef.current = window.setInterval(() => setRecordSeconds((s) => s + 1), 1000)
    } catch {
      setError('Could not access the microphone. Allow mic permission and try again.')
    }
  }

  function stopRecording() {
    if (!mediaRecorderRef.current || mediaRecorderRef.current.state === 'inactive') return
    if (timerRef.current) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
    setRecording(false)
    mediaRecorderRef.current.stop()
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }

  async function finishRecording(mime: string) {
    const blob = new Blob(chunksRef.current, { type: mime })
    chunksRef.current = []
    if (blob.size < 500) {
      setError('Recording was too short. Hold the button and speak, then stop.')
      return
    }
    setTranscribing(true)
    setError(null)
    try {
      const ext = mime.includes('mp4') ? 'recording.m4a' : mime.includes('ogg') ? 'recording.ogg' : 'recording.webm'
      const { text, engine } = await transcribeAudio(blob, ext)
      setTranscript((prev) => (prev.trim() ? `${prev.trim()}\n\n${text}` : text))
      setError(null)
      console.info(`Transcribed with ${engine}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Transcription failed')
    } finally {
      setTranscribing(false)
    }
  }

  if (!open) return null

  const busy = loading || transcribing

  async function handleGenerate() {
    setError(null)
    if (!transcript.trim()) {
      setError('Paste or record the doctor–patient conversation first.')
      return
    }
    if (!patientName.trim()) {
      setError('Patient name is required.')
      return
    }
    setLoading(true)
    try {
      const result = await generateSession({
        transcript: transcript.trim(),
        patientName: patientName.trim(),
        doctorName: doctorName.trim() || undefined,
        age: age ? Number(age) : undefined,
        sex: sex || undefined,
        mrn: mrn.trim() || undefined,
        consultationType: consultationType.trim() || undefined,
      })
      onGenerated(result.sessionId, result.session, result.listRow)
      setTranscript('')
      setPatientName('')
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Generation failed')
    } finally {
      setLoading(false)
    }
  }

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="new-session-title">
      <div className="modal-card">
        <div className="modal-header">
          <div>
            <h2 id="new-session-title">New session</h2>
            <p className="muted">Paste a transcript or record the consultation (Whisper).</p>
          </div>
          <button type="button" className="icon-btn" aria-label="Close" onClick={onClose} disabled={busy}>
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          <div className="record-row">
            {!recording ? (
              <button
                type="button"
                className="record-button"
                onClick={startRecording}
                disabled={busy}
              >
                <Mic size={18} />
                {transcribing ? 'Transcribing…' : 'Start recording'}
              </button>
            ) : (
              <button type="button" className="record-button active" onClick={stopRecording}>
                <Square size={16} fill="currentColor" />
                Stop · {formatTime(recordSeconds)}
              </button>
            )}
            <span className="muted record-hint">
              Uses Groq Whisper (same API key as `.env`). Text appears in the box below when you stop.
            </span>
          </div>

          <label className="field">
            <span>Conversation transcript</span>
            <textarea
              rows={8}
              placeholder="Doctor: …&#10;Patient: …&#10;&#10;Or use Start recording above."
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
              disabled={busy}
            />
          </label>

          <div className="field-grid">
            <label className="field">
              <span>Patient name *</span>
              <input value={patientName} onChange={(e) => setPatientName(e.target.value)} disabled={busy} />
            </label>
            <label className="field">
              <span>Clinician</span>
              <input value={doctorName} onChange={(e) => setDoctorName(e.target.value)} disabled={busy} />
            </label>
            <label className="field">
              <span>Age</span>
              <input type="number" min={0} value={age} onChange={(e) => setAge(e.target.value)} disabled={busy} />
            </label>
            <label className="field">
              <span>Sex</span>
              <select value={sex} onChange={(e) => setSex(e.target.value)} disabled={busy}>
                <option value="F">F</option>
                <option value="M">M</option>
                <option value="U">Unknown</option>
              </select>
            </label>
            <label className="field">
              <span>MRN (optional)</span>
              <input value={mrn} onChange={(e) => setMrn(e.target.value)} placeholder="Auto-generated if empty" disabled={busy} />
            </label>
            <label className="field">
              <span>Visit reason</span>
              <input value={consultationType} onChange={(e) => setConsultationType(e.target.value)} placeholder="e.g. cough consultation" disabled={busy} />
            </label>
          </div>

          {error && <p className="modal-error">{error}</p>}
          <p className="muted modal-hint">
            {loading
              ? 'Generating… This can take several minutes. SOAP and claims stream in the terminal; this dialog waits until finished.'
              : 'Keep python main.py running — recording and generation use the local API on port 8765.'}
          </p>
        </div>

        <div className="modal-footer">
          <button type="button" className="button secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="button" className="button primary" onClick={handleGenerate} disabled={busy}>
            {loading ? 'Generating…' : transcribing ? 'Transcribing…' : 'Generate'}
          </button>
        </div>
      </div>
    </div>
  )
}
