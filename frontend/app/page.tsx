'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { NewSessionModal } from '@/components/new-session-modal'
import { fetchSessionById, fetchSessionList, type SessionListRow } from '@/lib/api'
import { type LiveSessionPayload, useLiveSession } from '@/lib/live-session'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, Bell, BookOpen, Check, CheckCircle2, ChevronDown, ChevronRight, CircleHelp, ClipboardCheck, Copy, Download, FileText, Filter, GitBranch, HeartPulse, LayoutDashboard, Menu, Moon, MoreHorizontal, Network, PanelLeft, Search, Settings as SettingsIcon, ShieldCheck, SlidersHorizontal, Sparkles, Stethoscope, Sun, Users, X, XCircle, Zap } from 'lucide-react'

const doctors = [{ id: 'all', name: 'All clinicians' }, { id: 'd1', name: 'Dr. Maya Chen' }, { id: 'd2', name: 'Dr. Aaron Patel' }, { id: 'd3', name: 'Dr. Sofia Rivera' }]
const patients = [
  { id: 'p1', name: 'Jordan Williams', age: 42, sex: 'M', mrn: 'TN-20481', initials: 'JW', last: 'Today', sessions: 3, rate: 14 },
  { id: 'p2', name: 'Eleanor Brooks', age: 67, sex: 'F', mrn: 'TN-19732', initials: 'EB', last: 'Yesterday', sessions: 2, rate: 8 },
  { id: 'p3', name: 'Marcus Lee', age: 29, sex: 'M', mrn: 'TN-20114', initials: 'ML', last: 'Oct 08', sessions: 2, rate: 21 },
  { id: 'p4', name: 'Nadia Thompson', age: 54, sex: 'F', mrn: 'TN-18429', initials: 'NT', last: 'Oct 07', sessions: 4, rate: 11 },
  { id: 'p5', name: 'Priya Shah', age: 36, sex: 'F', mrn: 'TN-21008', initials: 'PS', last: 'Oct 04', sessions: 1, rate: 6 },
  { id: 'p6', name: 'Thomas Greene', age: 75, sex: 'M', mrn: 'TN-17663', initials: 'TG', last: 'Sep 29', sessions: 2, rate: 19 },
]
const sessions = [
  { id: 's-1042', patient: 'Jordan Williams', doctor: 'Dr. Maya Chen', time: 'Today, 9:42 AM', source: 'Phone', status: 'Ready for review', risk: 'high', claims: 14, rate: 21 },
  { id: 's-1041', patient: 'Eleanor Brooks', doctor: 'Dr. Aaron Patel', time: 'Yesterday, 3:18 PM', source: 'Upload', status: 'Signed off', risk: 'low', claims: 11, rate: 8 },
  { id: 's-1040', patient: 'Marcus Lee', doctor: 'Dr. Maya Chen', time: 'Oct 08, 11:05 AM', source: 'Phone', status: 'Signed off', risk: 'medium', claims: 18, rate: 17 },
  { id: 's-1039', patient: 'Nadia Thompson', doctor: 'Dr. Sofia Rivera', time: 'Oct 07, 4:31 PM', source: 'Text', status: 'Signed off', risk: 'low', claims: 9, rate: 6 },
]
const claims = [
  { id: 'c1', section: 'Subjective', label: 'Supported', text: 'Patient reports a dry cough for 5 days.', source: '“I have had this dry cough for about five days now.”', rationale: 'Directly stated by the patient.', flags: [] },
  { id: 'c2', section: 'Subjective', label: 'Supported', text: 'Cough is worse at night.', source: '“It is definitely worse at night.”', rationale: 'Directly stated by the patient.', flags: [] },
  { id: 'c3', section: 'Subjective', label: 'Contradicted', text: 'Patient reports a fever of 101.4°F.', source: '“I have not had a fever that I know of.”', rationale: 'The transcript explicitly denies fever.', flags: ['contradicted_by_source'] },
  { id: 'c4', section: 'Subjective', label: 'Unverifiable', text: 'Patient has a 20 pack-year smoking history.', source: 'No matching evidence found in transcript.', rationale: 'Smoking history was not discussed.', flags: ['invalid_or_missing_citation'] },
  { id: 'c5', section: 'Objective', label: 'Unverifiable', text: 'Lungs are clear to auscultation bilaterally.', source: 'No matching evidence found in transcript.', rationale: 'No physical exam was captured in the conversation.', flags: ['invalid_or_missing_citation'] },
  { id: 'c6', section: 'Assessment', label: 'Supported', text: 'Presentation is most consistent with a viral upper respiratory infection.', source: '“This sounds like a viral upper respiratory infection.”', rationale: 'Assessment is explicitly stated by the clinician.', flags: [] },
  { id: 'c7', section: 'Plan', label: 'Supported', text: 'Increase fluids and use honey for symptom relief.', source: '“Keep drinking fluids and try a teaspoon of honey.”', rationale: 'Plan is explicitly stated by the clinician.', flags: [] },
  { id: 'c8', section: 'Plan', label: 'Unverifiable', text: 'Start azithromycin 250 mg for 5 days.', source: 'No matching evidence found in transcript.', rationale: 'No antibiotic was prescribed in the conversation.', flags: ['invalid_or_missing_citation'] },
]
const trend = [{ day: 'Mon', rate: 18 }, { day: 'Tue', rate: 16 }, { day: 'Wed', rate: 17 }, { day: 'Thu', rate: 12 }, { day: 'Fri', rate: 14 }, { day: 'Sat', rate: 9 }, { day: 'Sun', rate: 11 }]
const verdictData = [{ name: 'Supported', value: 72, color: '#0f766e' }, { name: 'Unverifiable', value: 18, color: '#d97706' }, { name: 'Contradicted', value: 10, color: '#dc2626' }]
const nav = [{ key: 'dashboard', label: 'Overview', icon: LayoutDashboard }, { key: 'patients', label: 'Patients', icon: Users }, { key: 'sessions', label: 'Sessions', icon: FileText }, { key: 'evaluation', label: 'Evaluation', icon: ClipboardCheck }, { key: 'architecture', label: 'Architecture', icon: Network }, { key: 'integration', label: 'Integration', icon: Zap }]

function Verdict({ label }: { label: string }) { const Icon = label === 'Supported' ? CheckCircle2 : label === 'Contradicted' ? XCircle : AlertTriangle; return <span className={`verdict ${label.toLowerCase()}`}><Icon size={13} />{label}</span> }
function Metric({ label, value, change, trendDown, icon: Icon }: any) { return <div className="metric-card"><div className="metric-top"><span>{label}</span><span className="metric-icon"><Icon size={16} /></span></div><strong>{value}</strong><div className={trendDown ? 'metric-change positive' : 'metric-change'}>{trendDown ? <ArrowDownRight size={14} /> : <ArrowUpRight size={14} />}{change}</div></div> }
function Header({ onMenu, onPage, theme, setTheme }: any) { const [logoClicks, setLogoClicks] = useState(0); return <header className="topbar"><button className="mobile-menu" aria-label="Open navigation" onClick={onMenu}><Menu size={20} /></button><button className="brand" onClick={() => { setLogoClicks(logoClicks + 1); if (logoClicks === 4) alert('Primum non nocere.') }}><span className="brand-mark"><HeartPulse size={19} /></span><span>TrustNote</span></button><div className="breadcrumb"><span>Workspace</span><ChevronRight size={14} /><strong>Overview</strong></div><div className="top-actions"><button className="icon-btn" aria-label="Search"><Search size={18} /></button><button className="icon-btn" aria-label="Notifications"><Bell size={18} /></button><button className="theme-btn" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label="Toggle theme">{theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}</button><div className="view-select"><span className="online-dot" /> Viewing as <strong>Admin</strong><ChevronDown size={14} /></div><div className="avatar">AM</div></div></header> }
function Sidebar({ page, setPage, open }: any) { return <aside className={`sidebar ${open ? 'open' : ''}`}><div className="workspace"><div className="workspace-avatar">TN</div><div><strong>TrustNote Health</strong><span>Demo workspace</span></div><ChevronDown size={15} className="muted" /></div><nav>{nav.map(({ key, label, icon: Icon }) => <button key={key} className={page === key ? 'nav-item active' : 'nav-item'} onClick={() => setPage(key)}><Icon size={17} />{label}{key === 'sessions' && <span className="nav-count">4</span>}</button>)}</nav><div className="side-section"><span>WORKSPACE</span><button className="nav-item" onClick={() => setPage('settings')}><SettingsIcon size={17} />Settings</button><button className="nav-item" onClick={() => setPage('help')}><CircleHelp size={17} />Help center</button></div><div className="sidebar-bottom"><div className="demo-badge"><Sparkles size={15} /><div><strong>Demo data</strong><span>Synthetic records only</span></div></div><div className="profile"><div className="avatar">AM</div><div><strong>Alex Morgan</strong><span>Administrator</span></div><MoreHorizontal size={17} className="muted" /></div></div></aside> }
function Dashboard({ setPage, setSelectedSession, live }: { setPage: (p: string) => void; setSelectedSession: (id: string) => void; live?: LiveSessionPayload | null }) {
  const ws = live?.workspace
  const verdictDataLive = ws
    ? [
        { name: 'Supported', value: ws.verdictShares?.Supported ?? 0, color: '#0f766e' },
        { name: 'Unverifiable', value: ws.verdictShares?.Unverifiable ?? 0, color: '#d97706' },
        { name: 'Contradicted', value: ws.verdictShares?.Contradicted ?? 0, color: '#dc2626' },
      ]
    : verdictData
  const totalClaims = ws?.claimsVerified ?? 287
  const unsupported = ws ? `${ws.unsupportedRate}%` : '12.4%'
  const retention = ws ? `${ws.retentionRate}%` : '86.8%'
  const liveSessions = live
    ? [{ id: live.session.id, patient: live.patient.name, doctor: live.session.doctorName, time: live.session.time, source: live.session.source.replace('Manual transcript', 'Text'), status: live.session.status, risk: live.session.riskLevel, claims: live.session.totalClaims, rate: live.session.unsupportedPercentage }]
    : sessions
  return <div className="page-content"><div className="page-heading"><div><div className="eyebrow">Wednesday, October 11, 2026</div><h1>Good morning, Alex</h1><p>Here&apos;s the state of your clinical documentation workspace.</p></div><div className="heading-actions"><button className="button secondary"><Download size={16} />Export report</button><button className="button primary" onClick={() => setPage('sessions')}><FileText size={16} />View sessions</button></div></div><div className="demo-ribbon"><Sparkles size={15} /><span><strong>{live ? 'Live pipeline' : 'Demo data'}</strong> {live ? 'Metrics and session detail reflect your latest `python main.py` run.' : 'This workspace uses realistic synthetic clinical conversations for evaluation.'}</span><button>Learn more <ChevronRight size={14} /></button></div><div className="metrics"><Metric label="Sessions this week" value={live ? '1' : '24'} change={live ? 'Current terminal session' : '12.5% vs last week'} icon={Activity} /><Metric label="Claims verified" value={String(totalClaims)} change={live ? 'From NLI / verifier' : '8.2% vs last week'} trendDown icon={ShieldCheck} /><Metric label="Unsupported claim rate" value={unsupported} change={live ? 'Model-estimated' : '3.1% vs last week'} trendDown icon={AlertTriangle} /><Metric label="Pending reviews" value={live ? String(live.claims.filter(c => c.label !== 'Supported').length) : '7'} change="Needs clinician review" icon={Bell} /><Metric label="Avg. sentence retention" value={retention} change={live ? 'Supported claim share' : '1.4% vs last week'} trendDown icon={FileText} /></div><div className="chart-grid"><div className="panel trend-panel"><div className="panel-heading"><div><h2>Unsupported claim rate</h2><span>Last 7 days · model-estimated</span></div><button className="filter-button">This week <ChevronDown size={14} /></button></div><div className="chart-wrap"><ResponsiveContainer width="100%" height={220}><AreaChart data={trend} margin={{ left: -20, right: 8, top: 12 }}><defs><linearGradient id="fillRate" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#0f766e" stopOpacity={0.2} /><stop offset="100%" stopColor="#0f766e" stopOpacity={0} /></linearGradient></defs><CartesianGrid vertical={false} stroke="#e2e8f0" /><XAxis dataKey="day" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#64748b' }} /><YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#64748b' }} tickFormatter={(v) => `${v}%`} domain={[0, 25]} /><Tooltip formatter={(v) => [`${v}%`, 'Unsupported']} contentStyle={{ borderRadius: 10, border: '1px solid #e2e8f0', boxShadow: '0 8px 24px rgba(15,23,42,.08)' }} /><Area type="monotone" dataKey="rate" stroke="#0f766e" strokeWidth={2.5} fill="url(#fillRate)" /></AreaChart></ResponsiveContainer></div></div><div className="panel donut-panel"><div className="panel-heading"><div><h2>Claim verdicts</h2><span>All reviewed claims</span></div><button className="icon-btn"><MoreHorizontal size={18} /></button></div><div className="donut-content"><div className="donut"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={verdictDataLive} dataKey="value" innerRadius={58} outerRadius={78} paddingAngle={3} strokeWidth={0}>{verdictDataLive.map((item) => <Cell key={item.name} fill={item.color} />)}</Pie></PieChart></ResponsiveContainer><div className="donut-label"><strong>{totalClaims}</strong><span>claims</span></div></div><div className="legend">{verdictDataLive.map(item => <div key={item.name}><span className="legend-dot" style={{ backgroundColor: item.color }} /><span>{item.name}</span><strong>{item.value}%</strong></div>)}</div></div></div></div><div className="lower-grid"><div className="panel queue-panel"><div className="panel-heading"><div><h2>Needs review <span className="count-pill">7</span></h2><span>Prioritized by risk and verdict</span></div><button className="text-button" onClick={() => setPage('sessions')}>View all <ChevronRight size={14} /></button></div><div className="queue-list">{liveSessions.slice(0, 3).map((s, i) => <button className="queue-row" key={s.id} onClick={() => { setSelectedSession(s.id); setPage('session') }}><div className={`risk-bar ${s.risk}`} /><div className="queue-main"><strong>{s.patient}</strong><span>{s.doctor} · {s.time}</span></div><div className="queue-meta"><Verdict label={i === 0 ? 'Contradicted' : i === 1 ? 'Unverifiable' : 'Contradicted'} /><span>{s.claims} claims</span></div><ChevronRight size={16} className="muted" /></button>)}</div></div><div className="panel recent-panel"><div className="panel-heading"><div><h2>Recent sessions</h2><span>Latest activity</span></div><button className="text-button" onClick={() => setPage('sessions')}>View all <ChevronRight size={14} /></button></div><div className="mini-table">{liveSessions.map(s => <button className="mini-row" key={s.id} onClick={() => { setSelectedSession(s.id); setPage('session') }}><div className="patient-avatar">{live?.patient.name === s.patient ? live.patient.initials : patients.find(p => p.name === s.patient)?.initials}</div><div><strong>{s.patient}</strong><span>{s.time}</span></div><span className={`status-dot ${s.status === 'Ready for review' ? 'amber' : 'green'}`} /><span className="source">{s.source}</span></button>)}</div></div></div></div> }
function SessionsPage({
  setPage,
  setSelectedSession,
  apiSessions,
  onNewSession,
}: {
  setPage: (p: string) => void
  setSelectedSession: (id: string) => void
  apiSessions: SessionListRow[]
  onNewSession: () => void
}) {
  const demoExtra = { id: 's-1038', patient: 'Priya Shah', doctor: 'Dr. Maya Chen', time: 'Oct 04, 10:22 AM', source: 'Upload', status: 'Transcribing', risk: 'low', claims: 0, rate: 0 }
  const apiIds = new Set(apiSessions.map((s) => s.id))
  const merged = [...apiSessions, ...sessions.filter((s) => !apiIds.has(s.id)), demoExtra]
  return (
    <div className="page-content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">Workspace / Sessions</div>
          <h1>Sessions</h1>
          <p>Review transcription, claims, and note provenance.</p>
        </div>
        <button type="button" className="button primary" onClick={onNewSession}>
          <Activity size={16} />New session
        </button>
      </div>
      <div className="toolbar">
        <div className="search-field"><Search size={16} /><input placeholder="Search patients or sessions" /></div>
        <button className="filter-button"><Filter size={15} />Doctor <ChevronDown size={14} /></button>
        <button className="filter-button">Status <ChevronDown size={14} /></button>
        <button className="filter-button">Source <ChevronDown size={14} /></button>
      </div>
      <div className="panel table-panel">
        <div className="table-head"><span>Patient</span><span>Clinician</span><span>Started</span><span>Source</span><span>Status</span><span>Claims</span><span /></div>
        {merged.map((s) => (
          <button type="button" className="table-row" key={s.id} onClick={() => { setSelectedSession(s.id); setPage('session') }}>
            <div className="patient-cell">
              <div className="patient-avatar">{patients.find((p) => p.name === s.patient)?.initials || s.patient.slice(0, 2).toUpperCase()}</div>
              <div><strong>{s.patient}</strong><span>{s.id}</span></div>
            </div>
            <span>{s.doctor}</span><span>{s.time}</span>
            <span className="source"><span className="source-icon">{s.source === 'Phone' ? '◉' : s.source === 'Upload' ? '↑' : s.source === 'Web' ? '◎' : '≡'}</span>{s.source}</span>
            <span className={`status ${s.status === 'Ready for review' ? 'review' : s.status === 'Transcribing' ? 'progress' : 'signed'}`}>{s.status}</span>
            <span>{s.claims ? `${s.claims} claims` : '—'}</span>
            <ChevronRight size={16} className="muted" />
          </button>
        ))}
      </div>
    </div>
  )
}
function PatientsPage({ setPage }: any) { const [search, setSearch] = useState(''); const list = patients.filter(p => p.name.toLowerCase().includes(search.toLowerCase())); return <div className="page-content"><div className="page-heading"><div><div className="eyebrow">Workspace / Patients</div><h1>Patients</h1><p>Patient records and cross-clinician session history.</p></div><button className="button secondary"><Users size={16} />Export directory</button></div><div className="toolbar"><div className="search-field wide"><Search size={16} /><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search by name or MRN" /></div><span className="result-count">{list.length} patients · Demo data</span></div><div className="panel table-panel"><div className="table-head patient-head"><span>Patient</span><span>Demographics</span><span>MRN</span><span>Last session</span><span>Sessions</span><span>Unsupported rate</span><span /></div>{list.map(p => <button className="table-row patient-row" key={p.id} onClick={() => setPage('patient')}><div className="patient-cell"><div className="patient-avatar teal">{p.initials}</div><div><strong>{p.name}</strong><span>Patient ID {p.id}</span></div></div><span>{p.age} years · {p.sex}</span><span>{p.mrn}</span><span>{p.last}</span><span>{p.sessions}</span><span><span className={p.rate > 15 ? 'rate-high' : 'rate-ok'}>{p.rate}%</span></span><ChevronRight size={16} className="muted" /></button>)}</div></div> }
function SessionDetail({ onBack, live }: { onBack: () => void; live?: LiveSessionPayload | null }) {
  const [tab, setTab] = useState('Claims')
  const [filter, setFilter] = useState('All')
  const [expanded, setExpanded] = useState<string | null>(null)
  const claimRows = live?.claims?.length
    ? live.claims.map((c) => ({
        id: c.id,
        section: c.section,
        label: c.label,
        text: c.text,
        source: c.source || 'No matching evidence found in transcript.',
        rationale: c.rationale || 'Model verification output.',
        flags: c.flags || [],
      }))
    : claims
  const reviewCount = claimRows.filter((c) => c.label !== 'Supported').length
  const sess = live?.session
  const pat = live?.patient
  const turns = live?.transcript?.turns?.length ? live.transcript.turns : null
  return <div className="detail-page"><div className="detail-top"><button className="back-button" onClick={onBack}><ChevronRight size={16} className="rotate-180" />Back to sessions</button><div className="detail-actions"><button className="button secondary"><Copy size={15} />Copy note</button><button className="button secondary"><Download size={15} />Download <ChevronDown size={14} /></button><button className="button primary"><Check size={15} />Sign off note</button></div></div><div className="session-title"><div><div className="eyebrow">Session {sess?.id || 's-1042'} · {sess?.time || 'Today, 9:42 AM'}</div><h1>{pat?.name || 'Jordan Williams'} <span className="status review">{sess?.status || 'Ready for review'}</span></h1><p>{sess?.doctorName || 'Dr. Maya Chen'} · {sess?.specialty || 'General practice'} · {sess?.consultationType || '5-day cough consultation'}</p></div><div className="session-stats"><div><strong>{sess?.totalClaims ?? claimRows.length}</strong><span>claims</span></div><div><strong>{sess?.retentionRate ?? 78}%</strong><span>retained</span></div><div><strong>{sess?.unsupportedPercentage ?? 21}%</strong><span>unsupported</span></div></div></div><div className="detail-layout"><section className="transcript-panel panel"><div className="panel-heading"><div><h2>Transcript</h2><span>{sess?.transcriptModel || 'Whisper large-v3'} · {sess?.duration || '04:12'}</span></div><span className="live-badge"><span />{sess?.transcriptStatus || 'Complete'}</span></div><div className="transcript">{turns ? turns.map((t, idx) => <div className={`turn ${t.speaker === 'doctor' ? 'doctor-turn' : 'patient-turn'}`} key={idx}><div className={`speaker-avatar ${t.speaker === 'doctor' ? 'doctor' : ''}`}>{t.speakerInitials}</div><div><span className="turn-meta">{t.speakerName} <time>{t.timestamp}</time></span><p>{t.text}</p></div></div>) : <><div className="turn patient-turn"><div className="speaker-avatar">JW</div><div><span className="turn-meta">Jordan Williams <time>00:12</time></span><p>I have had this dry cough for about five days now. It is definitely worse at night, and it&apos;s keeping me up.</p></div></div><div className="turn doctor-turn"><div className="speaker-avatar doctor">MC</div><div><span className="turn-meta">Dr. Maya Chen <time>00:38</time></span><p>Any fever, shortness of breath, or chest pain?</p></div></div></>}</div></section><section className="claims-panel"><div className="tabs"><button className={tab === 'Claims' ? 'tab active' : 'tab'} onClick={() => setTab('Claims')}>Claims <span>{claimRows.length}</span></button><button className={tab === 'Note' ? 'tab active' : 'tab'} onClick={() => setTab('Note')}>Note</button><button className={tab === 'Review' ? 'tab active' : 'tab'} onClick={() => setTab('Review')}>Review <span className="tab-alert">{reviewCount}</span></button></div>{tab === 'Claims' && <><div className="claim-toolbar"><div><strong>Claim verification</strong><span>Each claim is traced to transcript evidence.</span></div><div className="claim-filters">{['All', 'Supported', 'Contradicted', 'Unverifiable'].map(f => <button key={f} className={filter === f ? 'filter-pill active' : 'filter-pill'} onClick={() => setFilter(f)}>{f}{f !== 'All' && <span>{claimRows.filter(c => c.label === f).length}</span>}</button>)}</div></div><div className="claims-list">{claimRows.filter(c => filter === 'All' || c.label === filter).map(c => <div className={`claim-card ${expanded === c.id ? 'expanded' : ''}`} key={c.id}><button className="claim-header" onClick={() => setExpanded(expanded === c.id ? null : c.id)}><span className="claim-section">{c.section}</span><span className="claim-text">{c.text}</span><Verdict label={c.label} /><ChevronDown size={15} className={expanded === c.id ? 'chevron-open' : ''} /></button>{expanded === c.id && <div className="claim-body"><div className="rationale"><strong>Rationale</strong><p>{c.rationale}</p></div><div className="evidence"><div className="evidence-head"><strong>Evidence</strong><span>{c.source.includes('No matching') ? '0 matches' : '1 match'}</span></div><blockquote>{c.source}</blockquote></div>{(c.flags?.length ?? 0) > 0 && <div className="flag-row"><AlertTriangle size={14} />{c.flags[0].replaceAll('_', ' ')}</div>}<div className="claim-actions"><button className="small-button"><Check size={13} />Accept</button><button className="small-button">Edit claim</button><button className="small-button danger"><X size={13} />Reject</button></div></div>}</div>)}</div></>}{tab === 'Note' && <NoteView live={live} claimRows={claimRows} />}{tab === 'Review' && <ReviewView claimRows={claimRows} reviewCount={reviewCount} />}</section></div><footer className="disclaimer">Draft for clinician review. Model-supported does not mean clinically approved.</footer></div> }
function soapSections(live?: LiveSessionPayload | null, which: 'original' | 'filtered' = 'original') {
  const note = live?.soapNote?.[which]
  if (!note) return null
  const keys = ['subjective', 'objective', 'assessment', 'plan'] as const
  return keys
    .map((k) => ({ title: k.charAt(0).toUpperCase() + k.slice(1), body: note[k]?.trim() }))
    .filter((s) => s.body)
}
function NoteView({ live, claimRows }: { live?: LiveSessionPayload | null; claimRows: typeof claims }) {
  const orig = soapSections(live, 'original')
  const filt = soapSections(live, 'filtered')
  const unsupported = new Set(claimRows.filter((c) => c.label !== 'Supported').map((c) => c.text))
  const strike = (text: string) => {
    if (!unsupported.size) return text
    return text.split(/(?<=[.!?])\s+/).map((sentence) => (unsupported.has(sentence.trim()) ? <del key={sentence}>{sentence} </del> : <span key={sentence}>{sentence} </span>))
  }
  return <div className="note-view"><div className="note-heading"><div><strong>SOAP note</strong><span>Original vs filtered output</span></div><span className="filtered-badge"><ShieldCheck size={14} />Filtered note</span></div><div className="note-columns"><div><span className="note-label">Original</span><div className="note-paper">{orig ? orig.map((s) => <div key={s.title}><h3>{s.title}</h3><p>{strike(s.body)}</p></div>) : <><h3>Subjective</h3><p>Patient reports a dry cough for 5 days, worse at night. <del>Patient reports a fever of 101.4°F.</del></p></>}</div></div><div><span className="note-label">Filtered</span><div className="note-paper filtered-paper">{filt ? filt.map((s) => <div key={s.title}><h3>{s.title}</h3><p>{s.body}</p></div>) : <><h3>Subjective</h3><p>Patient reports a dry cough for 5 days, worse at night.</p></>}</div></div></div></div>
}
function ReviewView({ claimRows, reviewCount }: { claimRows: typeof claims; reviewCount: number }) {
  return <div className="review-view"><div className="review-banner"><ShieldCheck size={18} /><div><strong>{reviewCount} claims need clinician review</strong><span>Accept, edit, or reject each flagged claim before sign-off.</span></div></div>{claimRows.filter(c => c.label !== 'Supported').map(c => <div className="review-row" key={c.id}><div><Verdict label={c.label} /><strong>{c.text}</strong></div><div><button className="small-button"><Check size={13} />Accept</button><button className="small-button">Edit</button><button className="small-button danger">Reject</button></div></div>)}</div>
}
function Architecture({ setPage }: any) { const nodes = ['Input', 'Transcript', 'SOAP generation', 'Atomic claims', 'Retrieval', 'Verification', 'Sentence guard', 'Filtered note', 'Evaluation']; return <div className="page-content"><div className="page-heading"><div><div className="eyebrow">System design</div><h1>Architecture</h1><p>How TrustNote moves from conversation to an auditable note.</p></div></div><div className="architecture-panel panel"><div className="flow-line">{nodes.map((node, i) => <div className="flow-node" key={node}><div className={`flow-icon ${i === 0 ? 'input' : i === 8 ? 'output' : ''}`}>{i === 0 ? <Activity size={18} /> : i === 8 ? <ClipboardCheck size={18} /> : <GitBranch size={18} />}</div><strong>{node}</strong><span>{i === 4 ? 'BM25 + RRF' : i === 5 ? 'LLM / NLI' : i === 6 ? 'Fail closed' : i === 7 ? 'Audit report' : 'Pipeline step'}</span>{i < nodes.length - 1 && <div className="flow-arrow">→</div>}</div>)}</div><div className="architecture-bottom"><div><h2>Fail-closed design</h2><p>TrustNote rejects truncated output, treats bad citations as Unverifiable, and never silently truncates a transcript or auto-retries a failed verification.</p><div className="principles"><span><CheckCircle2 size={14} />Bad citation → Unverifiable</span><span><CheckCircle2 size={14} />Transcript treated as data</span><span><CheckCircle2 size={14} />No silent truncation</span></div></div><div className="parameter-card"><strong>Retrieval parameters</strong><div><span>BM25</span><b>k1 1.5 · b 0.75</b></div><div><span>RRF</span><b>k 60 · top-k 5</b></div><div><span>Evidence windows</span><b>turn ±1</b></div></div></div></div><div className="panel planned-panel"><div className="planned-icon"><Zap size={18} /></div><div><strong>Whisper ASR integration</strong><p>Phone and upload ingestion are ready for connection. Audio transcription is marked planned in this demo.</p></div><span className="planned-badge">Planned</span></div></div> }
function Evaluation() { const bars = [{ name: 'Supported', p: .94, r: .91, f: .92 }, { name: 'Contradicted', p: .88, r: .81, f: .84 }, { name: 'Unverifiable', p: .76, r: .72, f: .74 }]; return <div className="page-content"><div className="page-heading"><div><div className="eyebrow">Quality lab · Demo data</div><h1>Evaluation</h1><p>Gold-labelled benchmarks for the note filtering pipeline.</p></div><button className="button secondary"><Download size={16} />Upload results</button></div><div className="gold-banner"><ShieldCheck size={17} /><div><strong>Human-labelled (gold)</strong><span>These metrics are based on seeded demo annotations. Model-estimated rates are shown separately.</span></div></div><div className="eval-grid"><div className="panel confusion"><div className="panel-heading"><div><h2>Confusion matrix</h2><span>Gold rows · predicted columns</span></div></div><div className="matrix"><div className="matrix-axis">PREDICTED →</div><div className="matrix-grid"><span /><span>Sup.</span><span>Cont.</span><span>Unver.</span><strong>Sup.</strong><b>0.89</b><b>0.04</b><b>0.07</b><strong>Cont.</strong><b>0.08</b><b>0.84</b><b>0.08</b><strong>Unver.</strong><b>0.06</b><b>0.11</b><b>0.83</b></div></div></div><div className="panel score-panel"><div className="panel-heading"><div><h2>Per-class scores</h2><span>Precision · recall · F1</span></div></div><div className="score-bars">{bars.map(b => <div key={b.name}><div className="score-title"><strong>{b.name}</strong><span>F1 {b.f}</span></div><div className="bar-row"><span>P</span><i><em style={{ width: `${b.p * 100}%` }} /></i><b>{b.p}</b></div><div className="bar-row"><span>R</span><i><em className="amber-bar" style={{ width: `${b.r * 100}%` }} /></i><b>{b.r}</b></div></div>)}</div></div></div><div className="eval-cards"><div className="eval-stat"><span>Macro F1</span><strong>0.83</strong><small>Human-labelled (gold)</small></div><div className="eval-stat"><span>Accuracy</span><strong>0.86</strong><small>Human-labelled (gold)</small></div><div className="eval-stat"><span>ROUGE-L F1</span><strong>0.78</strong><small>Baseline → filtered</small></div><div className="eval-stat"><span>Entity F1</span><strong>0.91</strong><small>Precision 0.93 · Recall 0.89</small></div></div><div className="panel compare-panel"><div className="panel-heading"><div><h2>Human unsupported claim rate</h2><span>Baseline vs filtered · gold labels</span></div></div><div className="compare-bars"><div><span>Baseline note</span><div><i style={{ width: '31%' }} /><strong>31.4%</strong></div></div><div><span>Filtered note</span><div><i className="teal-bar" style={{ width: '12%' }} /><strong>12.1%</strong></div></div></div><p className="limitation"><AlertTriangle size={14} />Limitation: human labels are based on a seeded evaluation set and may not represent clinical performance in production.</p></div></div> }
function Integration() { return <div className="page-content"><div className="page-heading"><div><div className="eyebrow">Future phone app</div><h1>Integration</h1><p>Connect capture clients to the TrustNote processing contract.</p></div><span className="planned-badge large">API preview</span></div><div className="integration-grid"><div className="panel contract-panel"><div className="panel-heading"><div><h2>Session contract</h2><span>Ready for a future phone client</span></div><button className="small-button"><Copy size={13} />Copy cURL</button></div><div className="endpoint"><span className="method post">POST</span><code>/api/sessions</code><pre>{`{\n  "doctorId": "d1",\n  "patientId": "p1",\n  "source": "phone"\n}`}</pre><div className="response"><span>201 response</span><code>{`{ "sessionId": "s-1042", "uploadUrl": "..." }`}</code></div></div><div className="endpoint"><span className="method put">PUT</span><code>{'{uploadUrl}'}</code><p>Upload audio using the signed URL returned by the session request.</p></div><div className="endpoint"><span className="method get">GET</span><code>/api/sessions/:id/status</code><p>Returns <code>{'{ status, progress }'}</code> as the session advances.</p></div><div className="endpoint"><span className="method get">GET</span><code>/api/sessions/:id/report</code><p>Returns the full note, claims, evidence, reviews, and metrics.</p></div></div><div className="side-stack"><div className="panel pair-panel"><div className="panel-heading"><div><h2>Pair a phone</h2><span>Demo pairing flow</span></div><span className="live-badge"><span />Ready</span></div><div className="pair-code">284 619</div><p>Enter this code in the TrustNote mobile app, or scan the QR placeholder.</p><div className="qr-placeholder"><div className="qr-inner">TN</div></div><button className="button secondary full">Generate new code</button></div><div className="panel feed-panel"><div className="panel-heading"><div><h2>Incoming feed</h2><span>Simulated session events</span></div><span className="live-badge"><span />Live</span></div><div className="feed-item"><span className="feed-pulse" /><div><strong>Jordan Williams</strong><span>Phone session · processing complete</span></div><span className="feed-time">now</span></div><div className="feed-item"><span className="feed-pulse amber-pulse" /><div><strong>Priya Shah</strong><span>Upload · transcribing</span></div><span className="feed-time">2m</span></div></div></div></div></div> }
function Settings() { return <div className="page-content"><div className="page-heading"><div><div className="eyebrow">Workspace / Settings</div><h1>Settings</h1><p>Configure verification defaults and review audit activity.</p></div><button className="button primary"><Check size={16} />Save changes</button></div><div className="settings-grid"><div className="panel settings-panel"><div className="setting-section"><h2>Verification defaults</h2><p>Applied to new sessions in this workspace.</p><label>Verifier<select><option>LLM verifier</option><option>NLI verifier</option></select></label><label>Provider<select><option>Vercel AI Gateway</option></select></label><div className="two-fields"><label>Top-k<input value="5" readOnly /></label><label>Window radius<input value="1 turn" readOnly /></label></div><div className="two-fields"><label>Entailment threshold<input value="0.85" readOnly /></label><label>Margin<input value="0.15" readOnly /></label></div></div><div className="setting-section"><h2>Appearance</h2><p>Theme preference for this workspace.</p><div className="theme-options"><button className="theme-option active"><Sun size={16} />Light</button><button className="theme-option"><Moon size={16} />Dark</button><button className="theme-option"><Sun size={16} />System</button></div></div></div><div className="panel audit-panel"><div className="panel-heading"><div><h2>Audit log</h2><span>Recent edits and sign-offs</span></div><button className="icon-btn"><MoreHorizontal size={18} /></button></div>{['Session s-1041 signed off', 'Claim c-22 edited', 'Verifier changed to LLM', 'Session s-1039 signed off'].map((item, i) => <div className="audit-row" key={item}><div className={`audit-icon ${i === 1 ? 'edit' : ''}`}>{i === 1 ? <FileText size={14} /> : <Check size={14} />}</div><div><strong>{item}</strong><span>{i === 0 ? 'Alex Morgan · Today, 10:06 AM' : 'Alex Morgan · Yesterday'}</span></div></div>)}</div></div></div> }

export default function Page() {
  const [page, setPage] = useState('dashboard')
  const [selectedSession, setSelectedSession] = useState('s-1042')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [theme, setTheme] = useState('light')
  const [modalOpen, setModalOpen] = useState(false)
  const [apiSessions, setApiSessions] = useState<SessionListRow[]>([])
  const [sessionCache, setSessionCache] = useState<Record<string, LiveSessionPayload>>({})
  const envelope = useLiveSession()
  const live = envelope?.status === 'ready' ? envelope.session ?? null : null
  const lastLiveAt = useRef(0)

  useEffect(() => {
    fetchSessionList().then(setApiSessions).catch(() => {})
  }, [])

  useEffect(() => {
    if (envelope?.status === 'ready' && envelope.session) {
      const id = envelope.session.session.id
      setSessionCache((prev) => ({ ...prev, [id]: envelope.session! }))
      if (envelope.updatedAt && envelope.updatedAt !== lastLiveAt.current) {
        lastLiveAt.current = envelope.updatedAt
        setSelectedSession(id)
        setPage('session')
      }
    }
  }, [envelope])

  useEffect(() => {
    if (page !== 'session') return
    if (sessionCache[selectedSession]) return
    if (live?.session.id === selectedSession) return
    const isDemo = sessions.some((s) => s.id === selectedSession)
    if (isDemo) return
    fetchSessionById(selectedSession).then((data) => {
      if (data) setSessionCache((prev) => ({ ...prev, [selectedSession]: data }))
    })
  }, [page, selectedSession, sessionCache, live])

  const activeSession =
    sessionCache[selectedSession] ??
    (live?.session.id === selectedSession ? live : undefined)

  const content = page === 'dashboard' ? <Dashboard setPage={setPage} setSelectedSession={setSelectedSession} live={live} /> : page === 'sessions' ? <SessionsPage setPage={setPage} setSelectedSession={setSelectedSession} apiSessions={apiSessions} onNewSession={() => setModalOpen(true)} /> : page === 'patients' ? <PatientsPage setPage={setPage} /> : page === 'session' ? <SessionDetail onBack={() => setPage('sessions')} live={activeSession} /> : page === 'evaluation' ? <Evaluation /> : page === 'architecture' ? <Architecture setPage={setPage} /> : page === 'integration' ? <Integration /> : page === 'settings' ? <Settings /> : <Dashboard setPage={setPage} setSelectedSession={setSelectedSession} live={live} />

  return (
    <div className={`app-shell ${theme === 'dark' ? 'dark-mode' : ''}`}>
      <Header onMenu={() => setMobileOpen(!mobileOpen)} onPage={setPage} theme={theme} setTheme={setTheme} />
      <Sidebar page={page} setPage={setPage} open={mobileOpen} />
      <main className="main-area">{content}</main>
      <NewSessionModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onGenerated={(sessionId, session, listRow) => {
          setSessionCache((prev) => ({ ...prev, [sessionId]: session }))
          if (listRow) {
            setApiSessions((prev) => [listRow, ...prev.filter((r) => r.id !== sessionId)])
          } else {
            fetchSessionList().then(setApiSessions)
          }
          setSelectedSession(sessionId)
          setPage('session')
        }}
      />
      <div className="keyboard-hint"><kbd>⌘</kbd><kbd>K</kbd><span>Quick search</span></div>
    </div>
  )
}

// Demo data intentionally lives in this file so the frontend prototype remains self-contained.
export { doctors, patients, sessions, claims }
