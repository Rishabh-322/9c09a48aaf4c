import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity, ArrowDownRight, ArrowLeft, ArrowRight, ArrowUpRight, BarChart3,
  CalendarDays, Check, ChevronDown, CircleHelp, Clock3, CloudDownload,
  Database, ExternalLink, FileChartColumnIncreasing, Gauge, Info,
  Layers, LayoutDashboard, Leaf, Menu, RefreshCcw, Search, ShieldCheck,
  Sparkles, Target, Wind, Zap,
} from 'lucide-react';
import {
  Area, CartesianGrid, ComposedChart, Line,
  ResponsiveContainer, Tooltip, XAxis, YAxis, Bar, BarChart,
} from 'recharts';
import type { CutoffComparison, Month, Period, Report, Stats, View } from './types';

const FIRST = '2026-01-02';
const LAST = '2026-02-01';
const DEFAULT_DAY = '2026-01-16';
const nf = new Intl.NumberFormat('en-GB', {maximumFractionDigits: 0});
const mw = (v: number | null | undefined, unit = 'MW') => v == null ? '—' : `${nf.format(Math.abs(v))} ${unit}`;
const signed = (v: number | null | undefined) => v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${nf.format(Math.abs(v))} MW`;
const localDate = (s: string, opts?: Intl.DateTimeFormatOptions) => new Date(s + 'T12:00:00Z').toLocaleDateString('en-GB', opts ?? {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'});
const plusDays = (s: string, n: number) => new Date(Date.parse(s+'T12:00:00Z') + n*86400000).toISOString().slice(0,10);
const dateLabel = (s: string) => localDate(s, {day: 'numeric', month: 'short', timeZone: 'UTC'});

async function getJSON<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {signal});
  if (!response.ok) {
    const body: {detail?: string} = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

function IconBadge({children, variant='mint'}: {children: React.ReactNode, variant?: 'mint'|'blue'|'amber'|'purple'}) {
  return <span className={`icon-badge ${variant}`}>{children}</span>;
}

function MetricCard({title, value, sub, icon, variant, footer}: {
  title: string; value: string; sub: string; icon: React.ReactNode;
  variant?: 'mint'|'blue'|'amber'|'purple'; footer?: string;
}) {
  return <article className="metric-card">
    <div className="metric-top"><span>{title}</span><IconBadge variant={variant}>{icon}</IconBadge></div>
    <div className="metric-value">{value}</div>
    <div className="metric-sub">{sub}</div>
    {footer && <div className="metric-footer"><span className="metric-dot" />{footer}</div>}
  </article>;
}

function LabelPill({status}: {status: Period['status']}) {
  const labels = {matched:'Matched', 'actual-only':'Actual only', 'forecast-only':'Forecast only', 'incomplete-actual':'Partial actual', missing:'No data'};
  return <span className={`status-pill ${status}`}>{status === 'matched' && <Check size={11} />}{labels[status]}</span>;
}

function ChartTooltip({active, payload, label}: {active?: boolean; payload?: {name?: string; value?: number; color?: string}[]; label?: string}) {
  if (!active || !payload?.length) return null;
  return <div className="chart-tooltip"><b>{label} UK</b>{payload.filter(p => p.value != null).map((p, i) =>
    <div key={i}><span className="tooltip-dot" style={{background:p.color}} />{p.name}<strong>{nf.format(p.value!)} MW</strong></div>
  )}</div>;
}

function PowerChart({data, compact=false}: {data: Period[]; compact?: boolean}) {
  const points = useMemo(() => data.map(p => ({...p, forecast: p.forecast_mw, actual: p.actual_mw})), [data]);
  return <div className={compact ? 'chart-wrap compact' : 'chart-wrap'}>
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={points} margin={{top: 12, right: 12, left: -16, bottom: 2}}>
        <defs>
          <linearGradient id="areaMint" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#19ae9b" stopOpacity={0.17}/><stop offset="100%" stopColor="#19ae9b" stopOpacity={0.005}/></linearGradient>
        </defs>
        <CartesianGrid stroke="#e9eef3" strokeDasharray="3 5" vertical={false}/>
        <XAxis dataKey="label" tick={{fill:'#8a96a7', fontSize:11}} tickLine={false} axisLine={false} interval={7} dy={10}/>
        <YAxis tick={{fill:'#8a96a7', fontSize:11}} tickLine={false} axisLine={false} tickFormatter={(v: number) => `${(v/1000).toFixed(0)}k`}/>
        <Tooltip content={<ChartTooltip />} cursor={{stroke:'#94a3b8',strokeDasharray:'3 4'}} />
        <Area type="linear" dataKey="actual" name="Actual" stroke="#0f9f91" strokeWidth={2.7} fill="url(#areaMint)" dot={false} connectNulls={false} isAnimationActive={false}/>
        <Line type="linear" dataKey="forecast" name="Forecast" stroke="#5266cc" strokeWidth={2.5} strokeDasharray="7 5" dot={{r: 3, fill: '#5266cc', stroke: '#fff', strokeWidth: 1}} connectNulls={false} isAnimationActive={false}/>
      </ComposedChart>
    </ResponsiveContainer>
  </div>;
}

function QualityPanel({stats}: {stats: Stats}) {
  const coverage = stats.coverage_pct;
  return <div className="quality-panel">
    <div className="panel-eyebrow">DATA QUALITY</div>
    <div className="quality-top"><strong>{coverage.toFixed(1)}%</strong><span>of hourly periods<br/>have complete matched pairs</span></div>
    <div className="progress-track"><div style={{width:`${coverage}%`}} /></div>
    <div className="quality-count"><span>{stats.matched_periods} matched</span><strong>{stats.total_periods} expected</strong></div>
    <div className="quality-note"><Info size={15}/><span>Accuracy is calculated only where a forecast and actual share the same target time.</span></div>
  </div>;
}

function DecisionBrief({report}: {report: Report}) {
  const brief = report.decision_brief;
  const matched = report.statistics.matched_periods;
  const complete = brief.status === 'complete';
  const net = brief.net_energy_error_mwh;
  const signal = net == null ? 'Insufficient matched data to describe wind-generation error'
    : net > 0 ? 'Forecast wind generation exceeded actual output'
    : net < 0 ? 'Actual wind generation exceeded the forecast' : 'Matched forecast and actual wind energy balanced';
  return <section className="decision-brief" aria-label="Analyst briefing">
    <div className="brief-main">
      <div className="brief-heading"><span className="panel-eyebrow">ANALYST BRIEF / RETROSPECTIVE</span><span className={`brief-quality ${complete ? 'complete' : 'limited'}`}>{complete ? 'Full coverage' : `${matched}/${report.statistics.total_periods} matched hours`}</span></div>
      <h2>{signal}</h2>
      <p>Evidence from {localDate(report.delivery_date)} using forecasts available at {report.cutoff_uk} UK on {localDate(report.decision_date)}. {brief.status === 'partial' ? 'Partial coverage: the totals below exclude missing hours.' : ''}</p>
      <div className="brief-foot"><Info size={15}/>{brief.limitation}</div>
    </div>
    <div className="brief-facts">
      <div><span>Net matched energy error</span><strong>{net == null ? '—' : `${net > 0 ? '+' : net < 0 ? '−' : ''}${nf.format(Math.abs(net))} MWh`}</strong><small>Forecast − actual, matched hours only</small></div>
      <div><span>Largest hourly miss</span><strong>{brief.largest_miss ? signed(brief.largest_miss.error_mw) : '—'}</strong><small>{brief.largest_miss ? `${brief.largest_miss.hour_uk} UK · absolute peak` : 'No comparable intervals'}</small></div>
      <div><span>Latest eligible publication</span><strong>{brief.latest_publication_utc ? `${brief.latest_publication_utc.slice(0,10)} ${brief.latest_publication_utc.slice(11,16)} UTC` : '—'}</strong><small>{brief.distinct_publications} distinct timestamps in selected forecasts</small></div>
    </div>
  </section>;
}

function EmptyState({error, retry}: {error?: string; retry: () => void}) {
  return <div className="empty-state">
    <div className="empty-icon"><Database size={30}/></div>
    <h3>{error ? 'Unable to load Elexon data' : 'No data returned for this period'}</h3>
    <p>{error ?? 'The source did not supply records for this selection. Missing periods will not be filled with estimates.'}</p>
    <button className="btn btn-primary" onClick={retry}><RefreshCcw size={16}/> Retry data request</button>
    <p className="empty-foot">For offline development, set <code>WINDSCOPE_DATA_MODE=demo</code> in the backend. Synthetic values will be prominently labeled.</p>
  </div>;
}

function App() {
  const [page, setPage] = useState<View>('overview');
  const [day, setDay] = useState(DEFAULT_DAY);
  const [cutoff, setCutoff] = useState('12:00');
  const [cachedReport, setReport] = useState<Report | null>(null);
  const [month, setMonth] = useState<Month | null>(null);
  const [loading, setLoading] = useState(true);
  const [monthLoading, setMonthLoading] = useState(false);
  const [monthRequested, setMonthRequested] = useState(false);
  const [error, setError] = useState('');
  const [monthError, setMonthError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [mobileNav, setMobileNav] = useState(false);
  const [query, setQuery] = useState('');
  const [onlyGaps, setOnlyGaps] = useState(false);
  const [comparison, setComparison] = useState<CutoffComparison | null>(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [comparisonError, setComparisonError] = useState('');
  const monthAbort = useRef<AbortController | null>(null);
  const comparisonAbort = useRef<AbortController | null>(null);

  const reload = useCallback(() => setRefresh(v => v + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    getJSON<Report>(`/api/analysis?delivery_date=${day}&cutoff=${cutoff}`, controller.signal)
      .then(data => {setReport(data); setLoading(false);})
      .catch(e => {if (!controller.signal.aborted) {setReport(null);setError(String(e.message));setLoading(false);}});
    return () => controller.abort();
  }, [day, cutoff, refresh]);

  useEffect(() => {
    monthAbort.current?.abort();
    setMonth(null); setMonthLoading(false); setMonthRequested(false); setMonthError('');
  }, [cutoff]);

  const loadMonth = useCallback(() => {
    monthAbort.current?.abort();
    const controller = new AbortController();
    monthAbort.current = controller;
    setMonthLoading(true); setMonthError(''); setMonthRequested(true);
    getJSON<Month>(`/api/month?cutoff=${cutoff}`, controller.signal)
      .then(data => {if (!controller.signal.aborted) {setMonth(data);setMonthLoading(false);}})
      .catch(e => {if (!controller.signal.aborted) {setMonthError(String(e.message));setMonthLoading(false);}});
  }, [cutoff]);

  useEffect(() => {
    comparisonAbort.current?.abort();
    setComparison(null); setComparisonLoading(false); setComparisonError('');
  }, [day, refresh]);

  const loadComparison = useCallback(() => {
    comparisonAbort.current?.abort();
    const controller = new AbortController();
    comparisonAbort.current = controller;
    setComparisonLoading(true); setComparisonError('');
    getJSON<CutoffComparison>(`/api/compare?delivery_date=${day}&early=09:00&late=18:00`, controller.signal)
      .then(data => {if (!controller.signal.aborted) {setComparison(data); setComparisonLoading(false);}})
      .catch(e => {if (!controller.signal.aborted) {setComparisonError(String(e.message)); setComparisonLoading(false);}});
  }, [day]);

  const navigate = (target: View) => {setPage(target); setMobileNav(false);};
  // Never display a previously fetched report under a newly selected date/cut-off.
  const report = cachedReport?.delivery_date === day && cachedReport?.cutoff_uk === cutoff ? cachedReport : null;
  const activeComparison = comparison?.delivery_date === day ? comparison : null;
  const activeMonth = month?.cutoff_uk === cutoff ? month : null;
  const stats = report?.statistics;
  const isDemo = report?.source.includes('DEMO');
  const filteredRows = (report?.periods ?? []).filter(r => (onlyGaps ? r.status !== 'matched' : true) && (r.label.includes(query) || r.status.includes(query.toLowerCase())));
  const mostUncertain = useMemo(() => (report?.periods ?? []).filter(p => p.error_mw != null).sort((a,b) => Math.abs(b.error_mw!) - Math.abs(a.error_mw!)).slice(0,3) ?? [], [report]);
  const navItems = [
    {id:'overview' as View, label:'Overview', icon:<LayoutDashboard size={19}/>},
    {id:'explorer' as View, label:'Forecast explorer', icon:<Activity size={19}/>},
    {id:'accuracy' as View, label:'Accuracy & risk', icon:<BarChart3 size={19}/>},
    {id:'methodology' as View, label:'Methodology', icon:<Layers size={19}/>},
  ];

  return <div className="app-shell">
    {mobileNav && <div className="mobile-overlay" onClick={() => setMobileNav(false)} />}
    <aside className={`sidebar ${mobileNav ? 'show':''}`}>
      <div className="brand"><div className="brand-mark"><Wind size={24}/></div><div><strong>windscope<span>.</span></strong><small>ENERGY INTELLIGENCE</small></div></div>
      <div className="sidebar-section-title">WORKSPACE</div>
      <nav className="main-nav" aria-label="Main navigation">
        {navItems.map(item => <button key={item.id} onClick={() => navigate(item.id)} className={`nav-link ${page === item.id?'selected':''}`}>
          {item.icon}<span>{item.label}</span>{page === item.id && <span className="nav-indicator"/>}
        </button>)}
      </nav>
      <div className="sidebar-section-title second">DATA SOURCES</div>
      <div className="source-list"><div><span className="source-dot"/><span>{!report ? 'Source pending' : isDemo ? 'Synthetic demonstration' : 'Elexon BMRS'}</span></div><div><Database size={16}/><span>WINDFOR / FUELHH</span></div></div>
      <div className="sidebar-bottom">
        <div className="help-card"><div className="help-logo"><Sparkles size={18}/></div><strong>Built for better decisions.</strong><p>Wind forecasting intelligence, grounded in what was known at purchase time.</p><button onClick={() => navigate('methodology')}>How it works <ArrowRight size={14}/></button></div>
        <div className="sidebar-credit"><span className="avatar">WS</span><span><b>WindScope Pilot</b><small>January 2026 · UK</small></span><ChevronDown size={15}/></div>
      </div>
    </aside>

    <main className="workspace">
      <header className="topbar">
        <div className="topbar-left"><button className="mobile-menu" aria-label="Open menu" onClick={() => setMobileNav(true)}><Menu size={22}/></button><span className="breadcrumb">Workspace</span><span className="breadcrumb-divider">/</span><b>{navItems.find(x => x.id===page)?.label}</b></div>
        <div className="topbar-right"><span className="scope-tag"><span/> JAN 2026 DECISIONS</span><a className="top-link" href="https://bmrs.elexon.co.uk/api-documentation" target="_blank" rel="noreferrer">Elexon API <ExternalLink size={14}/></a><div className="top-avatar">WS</div></div>
      </header>

      <div className="content">
        <div className="page-top">
          <div><div className="eyebrow"><span className="eyebrow-line"/> PROCUREMENT INTELLIGENCE / GREAT BRITAIN</div>
            <h1>{page==='overview'?'Wind generation overview':page==='explorer'?'Forecast explorer':page==='accuracy'?'Forecast accuracy & risk':'Data & methodology'}</h1>
            <p className="page-subtitle">{page==='overview'?'See the forecast your procurement team could actually act on.':page==='explorer'?'Inspect every timestamp, source publication and forecast revision.':page==='accuracy'?'Quantify forecast error and understand what uncertainty means.':'Transparent definitions, source lineage, and decision-time rules.'}</p>
          </div>
          <div className="page-actions"><button className="btn btn-quiet" onClick={reload} disabled={loading} title="Refresh selected delivery day"><RefreshCcw size={16} className={loading?'spinning':''}/> Refresh</button><a className="btn btn-primary" href={`/api/export?delivery_date=${day}&cutoff=${cutoff}`}><CloudDownload size={16}/> Export CSV</a></div>
        </div>

        {report && !isDemo && <div className="provenance-banner"><Database size={16}/><strong>ELEXON DATA</strong><span>{report.data_origin === 'local_snapshot' ? 'Local Elexon historical snapshot' : 'API response or HTTP cache'} · WINDFOR + WIND-filtered FUELHH · Retrospective analysis</span></div>}
        {isDemo && <div className="demo-banner"><Info size={18}/><strong>DEMONSTRATION DATA</strong><span>These numbers are synthetic examples, not Elexon measurements. Switch to live mode for assessment submission.</span></div>}
        <section className="context-bar" aria-label="Analysis controls">
          <div className="context-group"><CalendarDays size={18}/><label htmlFor="delivery-day">Delivery day</label><div className="date-picker-inline"><button aria-label="Previous delivery day" disabled={day<=FIRST} onClick={() => setDay(plusDays(day,-1))}><ArrowLeft size={15}/></button><input id="delivery-day" aria-label="Delivery date" type="date" min={FIRST} max={LAST} value={day} onChange={e => {if(e.target.value>=FIRST && e.target.value<=LAST)setDay(e.target.value);}}/><button aria-label="Next delivery day" disabled={day>=LAST} onClick={() => setDay(plusDays(day,1))}><ArrowRight size={15}/></button></div></div>
          <span className="context-divider"/>
          <div className="context-group"><Clock3 size={18}/><label htmlFor="cutoff">Decision cut-off</label><select id="cutoff" value={cutoff} onChange={e=>setCutoff(e.target.value)}>{['06:00','09:00','12:00','15:00','18:00','21:00'].map(x=><option key={x} value={x}>{x} UK</option>)}</select></div>
          <div className="context-note"><Info size={15}/><span>Cut-off is a scenario assumption, not a verified gate closure.</span></div>
        </section>
        <div className="decision-ribbon"><div className="ribbon-icon"><CalendarDays size={17}/></div><div><b>Decision made {report ? localDate(report.decision_date) : localDate(plusDays(day,-1))}</b><span>for delivery on {localDate(day)} · Based on forecasts published by {cutoff} UK time</span></div><span className="ribbon-time">D−1 DECISION</span></div>

        {(page==='overview' || page==='explorer' || page==='accuracy') && !report && !error ? <div className="loading-panel"><div className="loader"/><h3>Preparing decision-time analysis</h3><p>Retrieving and aligning WINDFOR forecasts with FUELHH actuals…</p></div> : null}
        {(page==='overview' || page==='explorer' || page==='accuracy') && !loading && !report ? <EmptyState error={error} retry={reload}/> : null}

        {page==='overview' && report && stats && <>
          <DecisionBrief report={report}/>
          <div className="metrics-grid">
            <MetricCard title="Forecast error (MAE)" value={mw(stats.mae)} sub="Mean absolute error" icon={<Target size={20}/>} variant="mint" footer={`${stats.matched_periods} matched intervals`} />
            <MetricCard title="Matched actual generation" value={mw(stats.actual_energy_mwh, 'MWh')} sub="Only hours with both forecast and actual" icon={<Zap size={20}/>} variant="blue" footer="Hourly mean MW × 1 hour" />
            <MetricCard title="Forecast bias" value={signed(stats.bias)} sub={stats.bias == null?'Insufficient matches':stats.bias>0?'Over-forecast on average':stats.bias<0?'Under-forecast on average':'No average bias'} icon={stats.bias != null && stats.bias>=0?<ArrowUpRight size={20}/>:<ArrowDownRight size={20}/>} variant="amber" footer="Forecast minus actual" />
            <MetricCard title="Match coverage" value={`${stats.coverage_pct.toFixed(1)}%`} sub={`${stats.matched_periods} of ${stats.total_periods} hourly intervals`} icon={<ShieldCheck size={20}/>} variant="purple" footer="Missing data never interpolated" />
          </div>
          <div className="dashboard-grid">
            <section className="panel main-chart-panel"><div className="panel-heading"><div><div className="panel-eyebrow">GENERATION MONITOR</div><h2>Forecast vs. actual generation</h2><p>Day-ahead decision snapshot · Hourly targets; actuals averaged from two half-hours</p></div><span className="chart-unit">MW</span></div>
              <div className="legend"><span><i className="legend-actual"/>Actual generation</span><span><i className="legend-forecast"/>Decision-time forecast</span></div>
              <PowerChart data={report.periods}/>
              <div className="chart-foot"><Info size={15}/> An hourly actual is shown only when both underlying half-hour measurements exist. No missing values are interpolated.</div>
            </section>
            <div className="right-stack"><QualityPanel stats={stats}/><section className="insight-panel"><div className="panel-eyebrow">PROCUREMENT INSIGHT</div><div className="insight-icon"><Activity size={23}/></div><h3>{stats.bias === null ? 'Insufficient forecast matches' : stats.bias > 0 ? 'Watch for over-forecasting' : stats.bias < 0 ? 'Watch for under-forecasting' : 'Balanced average forecast'}</h3><p>{stats.bias === null ? 'The selected cut-off produced no comparable forecast and actual values.' : stats.bias > 0 ? 'The selected forecast was higher than actual output on average. This can create unanticipated additional procurement requirements.' : stats.bias < 0 ? 'The selected forecast was below actual output on average. That can lead to purchasing more additional supply than necessary.' : 'Average signed error is close to zero. Individual intervals may still show substantial deviations.'}</p><button onClick={()=>navigate('accuracy')}>Explore forecast risk <ArrowRight size={15}/></button></section></div>
          </div>
          <div className="bottom-grid"><section className="panel smaller-panel"><div className="panel-heading"><div><div className="panel-eyebrow">RISK WINDOWS</div><h2>Largest absolute deviations</h2><p>Among matched intervals for the selected delivery day</p></div></div>
            <div className="risk-rows">{mostUncertain.length ? mostUncertain.map((p,i)=><div className="risk-row" key={p.time}><div className="risk-index">0{i+1}</div><div className="risk-info"><b>{p.label} <span>UK</span></b><small>Actual {mw(p.actual_mw)} · Forecast {mw(p.forecast_mw)}</small></div><span className={`risk-error ${p.error_mw!>0?'positive':''}`}>{signed(p.error_mw)}</span></div>):<p className="muted">No matched intervals available.</p>}</div>
          </section><section className="panel smaller-panel"><div className="panel-heading"><div><div className="panel-eyebrow">TRANSPARENT METRICS</div><h2>Decision confidence summary</h2><p>What the historical forecast tells us</p></div></div><div className="summary-list"><div><span>RMSE <CircleHelp size={13}/></span><strong>{mw(stats.rmse)}</strong></div><div><span>Mean absolute % error</span><strong>{stats.mape == null?'—':`${stats.mape.toFixed(1)}%`}</strong></div><div><span>Absolute deviation energy</span><strong>{mw(stats.absolute_error_mwh, 'MWh')}</strong></div><div><span>Latest permitted forecast</span><strong>≤ {cutoff} UK</strong></div></div><div className="summary-note">These are historical diagnostic metrics, not procurement volume recommendations.</div></section></div>
          <section className="panel scenario-panel">
            <div className="panel-heading"><div><div className="panel-eyebrow">DECISION-TIME SENSITIVITY</div><h2>Would a later forecast change the picture?</h2><p>Compare the information available at 09:00 vs 18:00 UK on the preceding day. Both are hypothetical decision times, not market gate closures.</p></div>
              <button className="btn btn-soft" disabled={comparisonLoading} onClick={loadComparison}>{comparisonLoading ? 'Comparing…' : 'Compare decision cut-offs'} <ArrowRight size={16}/></button>
            </div>
            {comparisonError && <p role="alert" className="error-text">{comparisonError}</p>}
            {activeComparison && <>
              <div className="scenario-grid">
                <div className="scenario-card"><span>EARLIER · {activeComparison.early.cutoff_uk} UK</span><strong>{mw(activeComparison.early.statistics.mae)}</strong><small>Historical mean absolute error · {activeComparison.early.statistics.coverage_pct}% coverage</small></div>
                <div className="scenario-card"><span>LATER · {activeComparison.late.cutoff_uk} UK</span><strong>{mw(activeComparison.late.statistics.mae)}</strong><small>Historical mean absolute error · {activeComparison.late.statistics.coverage_pct}% coverage</small></div>
                <div className="scenario-card"><span>FORECASTS REVISED</span><strong>{activeComparison.revised_hours} / {activeComparison.comparable_forecast_hours}</strong><small>Hours with a changed forecast in both scenarios</small></div>
                <div className="scenario-card"><span>NET FORECAST CHANGE</span><strong>{activeComparison.net_forecast_change_mwh == null ? '—' : `${activeComparison.net_forecast_change_mwh > 0 ? '+' : ''}${nf.format(activeComparison.net_forecast_change_mwh)} MWh`}</strong><small>Change in hourly forecast energy for comparable hours</small></div>
              </div>
              <div className="paired-comparison" role="status">
                <div><span className="panel-eyebrow">LIKE-FOR-LIKE COMPARISON</span><h3>{activeComparison.common_comparison.outcome === 'later_better' ? 'Later forecast was more accurate on matched hours' : activeComparison.common_comparison.outcome === 'later_worse' ? 'Earlier forecast was more accurate on matched hours' : activeComparison.common_comparison.outcome === 'unchanged' ? 'Both cut-offs had identical average error' : 'Insufficient common matched hours'}</h3><p>Compare the <b>same {activeComparison.common_comparison.matched_hours} hourly targets</b> at both cut-offs, avoiding misleading comparisons when coverage changes.</p></div>
                <div className="paired-number"><strong>{activeComparison.common_comparison.delta_mae_mw == null ? '—' : signed(activeComparison.common_comparison.delta_mae_mw)}</strong><span>Later − earlier paired MAE<br/>Positive = later was worse</span></div>
              </div>
              <div className="scenario-note"><Info size={16}/> {activeComparison.note} A lower historical MAE for one day does not guarantee a better purchasing outcome.</div>
            </>}
          </section>
        </>}

        {page==='explorer' && report && stats && <>
          <div className="explorer-summary"><div><span>AVAILABLE FORECASTS</span><b>{stats.forecast_periods} <small>/ {stats.total_periods}</small></b></div><div><span>AVAILABLE ACTUALS</span><b>{stats.actual_periods} <small>/ {stats.total_periods}</small></b></div><div><span>MATCHED PERIODS</span><b>{stats.matched_periods} <small>/ {stats.total_periods}</small></b></div><div><span>FORECAST CUTOFF</span><b>{cutoff} <small>UK</small></b></div></div>
          <section className="panel explorer-chart"><div className="panel-heading"><div><div className="panel-eyebrow">DELIVERY CURVE</div><h2>Intraday generation profile</h2><p>{dateLabel(day)} · Forecast values published before the selected decision time</p></div></div><div className="legend"><span><i className="legend-actual"/>Actual generation</span><span><i className="legend-forecast"/>Decision-time forecast</span></div><PowerChart data={report.periods} compact /></section>
          <section className="panel data-panel"><div className="panel-heading table-title"><div><div className="panel-eyebrow">SOURCE TRACEABILITY</div><h2>Hourly comparison and source outturn</h2><p>Each hourly actual averages two complete FUELHH half-hours (shown separately).</p></div><span className="row-total">{filteredRows.length} ROWS</span></div>
            <div className="table-controls"><div className="search-box"><Search size={16}/><input aria-label="Search periods" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search time or status…" /></div><label className="toggle-label"><input type="checkbox" checked={onlyGaps} onChange={e=>setOnlyGaps(e.target.checked)}/> Show gaps only</label></div>
            <div className="table-scroll"><table><thead><tr><th>HOUR (UK)</th><th>FORECAST</th><th>ACTUAL (HOURLY)</th><th>ACTUAL :00</th><th>ACTUAL :30</th><th>SIGNED ERROR</th><th>FORECAST PUBLISHED (UTC)</th><th>QUALITY</th></tr></thead><tbody>{filteredRows.map(p=><tr key={p.time}><td className="table-time">{p.label}</td><td>{mw(p.forecast_mw)}</td><td>{mw(p.actual_mw)}</td><td>{mw(p.actual_half_hours_mw[0])}</td><td>{mw(p.actual_half_hours_mw[1])}</td><td className={p.error_mw == null?'faded':p.error_mw>0?'up':'down'}>{signed(p.error_mw)}</td><td className="table-mono">{p.published_at ? p.published_at.slice(0,16).replace('T',' ')+' UTC':'—'}</td><td><LabelPill status={p.status}/></td></tr>)}</tbody></table>{filteredRows.length===0&&<div className="no-rows">No periods match your filters.</div>}</div>
          </section>
        </>}

        {page==='accuracy' && report && stats && <>
          <section className="accuracy-lead"><div><div className="panel-eyebrow">MONTHLY PERFORMANCE</div><h2>January purchase-decision window</h2><p>31 decision days · Deliveries from 2 January to 1 February 2026. Metrics aggregate matched periods only.</p></div><button className="btn btn-primary" onClick={loadMonth} disabled={monthLoading}>{monthLoading?<RefreshCcw className="spinning" size={16}/>:<FileChartColumnIncreasing size={16}/>} {monthLoading?'Calculating month…':activeMonth?'Recalculate month':'Calculate monthly accuracy'}</button></section>
          {!activeMonth && <div className="month-placeholder"><div className="month-placeholder-icon"><BarChart3 size={32}/></div><h3>{monthLoading?'Aggregating decision-time forecasts…':'Run the month-wide accuracy assessment'}</h3><p>{monthLoading?'Fetching 31 delivery days with bounded requests. Subsequent analyses use the backend cache.':'The monthly assessment retrieves historical Elexon data and evaluates only the forecast values that were available before each decision cut-off.'}</p>{monthError&&<div className="error-text">{monthError}</div>}{!monthLoading&&<button className="btn btn-soft" onClick={loadMonth}>{monthRequested ? 'Retry monthly analysis' : 'Generate performance report'} <ArrowRight size={16}/></button>}</div>}
          {activeMonth && <><div className="metrics-grid month-metrics"><MetricCard title="Monthly MAE" value={mw(activeMonth.statistics.mae)} sub="Matched intervals, all delivery days" icon={<Target size={20}/>} variant="mint"/><MetricCard title="Monthly RMSE" value={mw(activeMonth.statistics.rmse)} sub="Penalises larger misses" icon={<Gauge size={20}/>} variant="blue"/><MetricCard title="Monthly bias" value={signed(activeMonth.statistics.bias)} sub="Positive means over-forecast" icon={<Activity size={20}/>} variant="amber"/><MetricCard title="Matched coverage" value={`${activeMonth.statistics.coverage_pct.toFixed(1)}%`} sub={`${activeMonth.statistics.matched_periods} of ${activeMonth.statistics.total_periods}`} icon={<ShieldCheck size={20}/>} variant="purple"/></div>
            <section className="panel monthly-chart"><div className="panel-heading"><div><div className="panel-eyebrow">DAILY ERROR ANALYSIS</div><h2>Forecast accuracy across decision dates</h2><p>Daily mean absolute error (MW) · Gaps shown when no comparison is possible</p></div></div><div className="chart-wrap monthly"><ResponsiveContainer width="100%" height="100%"><BarChart data={activeMonth.days.map(d=>({...d,day:dateLabel(d.delivery_date)}))} margin={{top:15,right:10,left:-15,bottom:0}}><CartesianGrid vertical={false} stroke="#e9eef3" strokeDasharray="3 4"/><XAxis dataKey="day" interval={4} tickLine={false} axisLine={false} tick={{fill:'#8795a7',fontSize:11}}/><YAxis tickLine={false} axisLine={false} tick={{fill:'#8795a7',fontSize:11}}/><Tooltip content={<ChartTooltip/>}/><Bar dataKey="mae" name="MAE" fill="#1aa996" radius={[5,5,0,0]} maxBarSize={26}/></BarChart></ResponsiveContainer></div></section>
            <section className="panel monthly-table"><div className="panel-heading"><div><div className="panel-eyebrow">MONTHLY AUDIT</div><h2>Daily scorecard</h2><p>Click any delivery date to inspect the underlying points</p></div></div><div className="table-scroll"><table><thead><tr><th>DELIVERY DATE</th><th>MAE</th><th>RMSE</th><th>BIAS</th><th>MATCH COVERAGE</th><th></th></tr></thead><tbody>{activeMonth.days.map(d=><tr key={d.delivery_date} className="clickable-row" tabIndex={0} role="button" aria-label={`Open hourly data for ${d.delivery_date}`} onKeyDown={e => {if (e.key === 'Enter' || e.key === ' ') {e.preventDefault();setDay(d.delivery_date);navigate('explorer');}}} onClick={()=>{setDay(d.delivery_date);navigate('explorer')}}><td className="table-time">{localDate(d.delivery_date)}</td><td>{mw(d.mae)}</td><td>{mw(d.rmse)}</td><td>{signed(d.bias)}</td><td>{d.coverage_pct.toFixed(1)}%</td><td><ArrowRight size={16}/></td></tr>)}</tbody></table></div></section></>}
        </>}

        {page==='methodology' && <>
          <section className="method-intro"><div className="method-icon"><ShieldCheck size={31}/></div><div><div className="panel-eyebrow">AUDITABLE BY DESIGN</div><h2>Every result has a defensible data trail.</h2><p>This pilot deliberately distinguishes observed generation, previously published forecasts, and the procurement-time information boundary. No AI-generated predictions are used.</p></div></section>
          <div className="method-grid">
            <div className="panel method-card"><span className="method-num">01 / DATA INGESTION</span><h3>Two Elexon datasets</h3><p><strong>FUELHH</strong> is the actual half-hourly generation feed, filtered to <code>fuelType = WIND</code>. <strong>WINDFOR</strong> contains forecasts with both target <code>startTime</code> and publication <code>publishTime</code>.</p><a href="https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream" target="_blank" rel="noreferrer">View WINDFOR docs <ExternalLink size={14}/></a></div>
            <div className="panel method-card"><span className="method-num">02 / INFORMATION BOUNDARY</span><h3>Strict as-of selection</h3><p>For each forecast target time, select the latest publication at or before the configured cut-off on the previous UK calendar day. Future publications are excluded to prevent look-ahead bias.</p><div className="code-example">publishTime ≤ decisionCutoff</div></div>
            <div className="panel method-card"><span className="method-num">03 / ACCURACY</span><h3>Compare like for like</h3><p>WINDFOR has hourly targets and FUELHH has half-hour values. For hour H, hourly actual MW = mean(FUELHH at H, FUELHH at H+30m). Both readings must exist; gaps are never filled.</p><div className="code-example">hourly error = hourly forecast − hourly mean actual</div></div>
            <div className="panel method-card"><span className="method-num">04 / INTEGRITY</span><h3>Visible limitations</h3><p>Coverage is always displayed next to error. MAPE excludes intervals with zero actual generation. Signed bias flags the direction of forecast error. Estimates of demand, prices and procurement quantities are intentionally out of scope.</p><div className="code-example">coverage = matched / expected</div></div>
          </div>
          <section className="panel formula-panel"><div className="panel-eyebrow">FORMULA REFERENCE</div><h2>Accuracy metric definitions</h2><div className="formula-grid"><div><b>MAE</b><p>Mean of the absolute forecast errors.</p><code>mean(|F − A|)</code></div><div><b>RMSE</b><p>Square root of mean squared error.</p><code>sqrt(mean((F − A)²))</code></div><div><b>Bias</b><p>Signed mean error: positive = forecast too high.</p><code>mean(F − A)</code></div><div><b>MAPE</b><p>Percentage error, excluding zero actual values.</p><code>mean(|F − A| / A) × 100</code></div></div></section>
          <div className="disclaimer"><Info size={17}/><p><strong>Operational interpretation:</strong> This is an analytical pilot, not a real electricity trading system. The 12:00 UK default is a user-adjustable hypothetical procurement decision cut-off. The assessment provides only wind forecast and actual data; it cannot calculate actual purchase requirements without consumer demand and other available generation.</p></div>
        </>}
        <footer className="footer"><span><Leaf size={14}/> WindScope © 2026 · Product engineering pilot</span><span>Contains BMRS data © Elexon Limited copyright and database right 2026 · <a href="https://www.elexon.co.uk/bsc/data/balancing-mechanism-reporting-agent/copyright-licence-bmrs-data/" target="_blank" rel="noreferrer">BMRS data licence <ExternalLink size={12}/></a> · Europe/London</span></footer>
      </div>
    </main>
  </div>;
}

export default App;
