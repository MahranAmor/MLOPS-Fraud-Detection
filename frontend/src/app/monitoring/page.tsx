'use client';

import { useState, useEffect, useRef, useCallback } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://api.fraud.local';
const GRAFANA_URL = 'http://localhost:3001';
const GRAFANA_UID = 'mlops-fraud-monitoring';
const GRAFANA_SLUG = 'mlops-fraud-detection-e28094-monitoring';
const REFRESH_INTERVAL = 30000;

type DriftStatus = {
  drift_detected: boolean;
  status: string;
  last_check: string | null;
  report_available: boolean;
};

type ModelMetadata = {
  model_name: string;
  version: string;
  source: string;
  loaded_at: string;
  mlflow_run_id: string;
  stage: string;
  algorithm: string;
  features_count: number;
};

type HealthStatus = {
  status: string;
  model_loaded: boolean;
  preprocessor_loaded: boolean;
};

type MetricsSummary = {
  fraud_rate: number;
  predictions_fraud: number;
  predictions_legit: number;
  prediction_latency_p50: number;
  prediction_latency_p95: number;
  prediction_latency_p99: number;
  prediction_errors: number;
  model_loaded: number;
  drift_score: number;
  drift_detected: number;
  drift_features_count: number;
  http_requests_total: number;
  k8s_running_pods: number;
  k8s_pending_pods: number;
  k8s_failed_pods: number;
  k8s_restart_pods: number;
  k8s_cpu_by_pod: Record<string, number>;
  k8s_mem_by_pod: Record<string, number>;
};

type Tab = 'overview' | 'report';

function fmt(n: number, decimals = 0): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
  return n.toFixed(decimals);
}

function msLabel(s: number): string {
  if (!s || s < 0.0001) return '—';
  return (s * 1000).toFixed(0) + ' ms';
}

function bytesLabel(b: number): string {
  if (!b) return '0 B';
  if (b >= 1024 * 1024 * 1024) return (b / (1024 * 1024 * 1024)).toFixed(1) + ' GB';
  if (b >= 1024 * 1024) return (b / (1024 * 1024)).toFixed(1) + ' MiB';
  if (b >= 1024) return (b / 1024).toFixed(1) + ' KiB';
  return b.toFixed(0) + ' B';
}

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (data.length < 2) return null;
  const w = 200, h = 38, pad = 2;
  const max = Math.max(...data, 0.001);
  const min = Math.min(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return `${x},${y}`;
  });
  const area = `M${pad},${h - pad} L${pts.join(' L')} L${w - pad},${h - pad} Z`;
  const colorId = color.replace(/[^a-z0-9]/gi, '');
  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: '100%', height: h }} preserveAspectRatio="none">
      <defs>
        <linearGradient id={`g${colorId}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.15" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#g${colorId})`} />
      <polyline points={pts.join(' ')} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function Gauge({ value, max = 1, color }: { value: number; max?: number; color: string }) {
  const pct = Math.min(value / max, 1);
  const r = 34, cx = 46, cy = 44;
  const circ = Math.PI * r;
  const offset = circ * (1 - pct);
  const display = max === 1 ? `${(value * 100).toFixed(1)}%` : value.toFixed(2);
  return (
    <svg viewBox="0 0 92 52" style={{ width: 110, height: 64 }}>
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`} fill="none" stroke="var(--border)" strokeWidth="6" strokeLinecap="round" />
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`} fill="none" stroke={color} strokeWidth="6" strokeLinecap="round"
        strokeDasharray={circ} strokeDashoffset={offset}
        style={{ transition: 'stroke-dashoffset 0.7s cubic-bezier(.4,0,.2,1)' }} />
      <text x={cx} y={cy - 2} textAnchor="middle" fontSize="12" fontWeight="800" fill="var(--text-1)" fontFamily="var(--font-sans)">{display}</text>
    </svg>
  );
}

function SectionLabel({ icon, label }: { icon: string; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14, marginTop: 28 }}>
      <span style={{ fontSize: 14 }}>{icon}</span>
      <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase' as const, color: 'var(--text-3)' }}>{label}</span>
      <div style={{ flex: 1, height: 1, background: 'var(--border)', marginLeft: 4 }} />
    </div>
  );
}

function MetricCard({ label, value, sub, color = 'var(--accent)', sparkData, badge, badgeClass = 'badge-blue' }: {
  label: string; value: string; sub?: string; color?: string;
  sparkData?: number[]; badge?: string; badgeClass?: string;
}) {
  return (
    <div className="card" style={{ padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' as const, color: 'var(--text-3)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        {label}
        {badge && <span className={`badge ${badgeClass}`} style={{ fontSize: 10 }}>{badge}</span>}
      </div>
      <div style={{ fontSize: 26, fontWeight: 800, color: 'var(--text-1)', letterSpacing: '-1px', lineHeight: 1.1, fontFamily: 'var(--font-sans)' }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>{sub}</div>}
      {sparkData && sparkData.length > 1 && <div style={{ marginTop: 8 }}><Sparkline data={sparkData} color={color} /></div>}
    </div>
  );
}

// Pod bar chart
function PodBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.min(value / max, 1) : 0;
  const shortLabel = label.replace(/fraud-(backend|frontend)-\w+/, (_, t) => t === 'backend' ? '⬡ backend' : '◈ frontend');
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '70%' }}>{shortLabel}</span>
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-1)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>{label.includes('cpu') ? `${(value * 1000).toFixed(1)}m` : bytesLabel(value)}</span>
      </div>
      <div style={{ height: 6, borderRadius: 4, background: 'var(--border)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct * 100}%`, background: color, borderRadius: 4, transition: 'width 0.5s ease' }} />
      </div>
    </div>
  );
}

export default function MonitoringPage() {
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [driftStatus, setDriftStatus] = useState<DriftStatus | null>(null);
  const [modelMeta, setModelMeta] = useState<ModelMetadata | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const histRef = useRef({ fraud: [] as number[], latency: [] as number[], reqs: [] as number[] });

  const fetchAll = useCallback(async (silent = false) => {
    if (!silent) setRefreshing(true);
    try {
      const [dr, mr, hr, ms] = await Promise.allSettled([
        fetch(`${API_URL}/drift-status`).then(r => r.json()),
        fetch(`${API_URL}/model-metadata`).then(r => r.json()),
        fetch(`${API_URL}/health`).then(r => r.json()),
        fetch(`${API_URL}/metrics-summary`).then(r => r.json()).catch(() => null),
      ]);
      if (dr.status === 'fulfilled') setDriftStatus(dr.value);
      if (mr.status === 'fulfilled') setModelMeta(mr.value);
      if (hr.status === 'fulfilled') setHealth(hr.value);
      if (ms.status === 'fulfilled' && ms.value) {
        const m = ms.value as MetricsSummary;
        const h = histRef.current;
        h.fraud   = [...h.fraud.slice(-19),  m.fraud_rate];
        h.latency = [...h.latency.slice(-19), m.prediction_latency_p50];
        h.reqs    = [...h.reqs.slice(-19),    m.http_requests_total];
        setMetrics(m);
      }
      setLastRefresh(new Date());
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const id = setInterval(() => fetchAll(true), REFRESH_INTERVAL);
    return () => clearInterval(id);
  }, [fetchAll]);

  const isDrift = driftStatus?.drift_detected ?? false;
  const h = histRef.current;
  const fraudRate = metrics?.fraud_rate ?? 0;
  const totalPreds = (metrics?.predictions_fraud ?? 0) + (metrics?.predictions_legit ?? 0);

  const cpuPods = Object.entries(metrics?.k8s_cpu_by_pod ?? {}).filter(([k]) => k);
  const memPods = Object.entries(metrics?.k8s_mem_by_pod ?? {}).filter(([k]) => k);
  const maxCpu = Math.max(...cpuPods.map(([, v]) => v), 0.001);
  const maxMem = Math.max(...memPods.map(([, v]) => v), 1);

  const tabs: { id: Tab; icon: string; label: string }[] = [
    { id: 'overview', icon: '◈', label: 'Live Metrics' },
    { id: 'report',   icon: '≋', label: 'Evidently Report' },
  ];

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>

      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div>
            <h1 className="section-title">
              <span style={{ width: 42, height: 42, borderRadius: 12, background: 'rgba(45,91,227,0.1)', border: '1px solid rgba(45,91,227,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, color: 'var(--accent)', flexShrink: 0 }}>◈</span>
              Monitoring
            </h1>
            <p className="section-subtitle">Real-time model performance, data drift detection and Evidently reports.</p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4, flexShrink: 0 }}>
            {lastRefresh && <span style={{ fontSize: 11, color: 'var(--text-4)', fontFamily: 'var(--font-mono)' }}>{lastRefresh.toLocaleTimeString()}</span>}
            <button className="btn-secondary" onClick={() => fetchAll()} disabled={refreshing} style={{ padding: '7px 14px', fontSize: 12, gap: 6 }}>
              <span style={{ display: 'inline-block', animation: refreshing ? 'spin 0.65s linear infinite' : 'none' }}>↻</span>
              Refresh
            </button>
            <a href={`${GRAFANA_URL}/d/${GRAFANA_UID}/${GRAFANA_SLUG}?orgId=1&refresh=30s`} target="_blank" rel="noreferrer" className="btn-primary" style={{ padding: '7px 14px', fontSize: 12, textDecoration: 'none' }}>
              ↗ Grafana
            </a>
          </div>
        </div>
      </div>

      {/* Drift Banner */}
      {!loading && driftStatus && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 20px', borderRadius: 'var(--radius)', marginBottom: 24, background: isDrift ? 'var(--fraud-bg)' : 'var(--safe-bg)', border: `1px solid ${isDrift ? 'var(--fraud-border)' : 'var(--safe-border)'}` }}>
          <span style={{ fontSize: 18 }}>{isDrift ? '🚨' : '✅'}</span>
          <div>
            <span style={{ fontWeight: 700, fontSize: 14, color: isDrift ? 'var(--fraud)' : 'var(--safe)' }}>{isDrift ? 'Data Drift Detected' : 'Data Stable'}</span>
            {driftStatus.last_check && <span style={{ fontSize: 12, color: 'var(--text-3)', marginLeft: 12 }}>Last check: {new Date(driftStatus.last_check).toLocaleString()}</span>}
          </div>
          <span className={`badge ${isDrift ? 'badge-fraud' : 'badge-safe'}`} style={{ marginLeft: 'auto' }}>{driftStatus.status}</span>
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 28, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 4 }}>
        {tabs.map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)} style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '9px 16px', borderRadius: 9, border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600, fontFamily: 'var(--font-sans)', transition: 'all 0.15s ease', background: activeTab === tab.id ? 'var(--bg)' : 'transparent', color: activeTab === tab.id ? 'var(--text-1)' : 'var(--text-3)', boxShadow: activeTab === tab.id ? 'var(--shadow-sm)' : 'none' }}>
            <span>{tab.icon}</span>{tab.label}
          </button>
        ))}
      </div>

      {/* TAB: LIVE METRICS */}
      {activeTab === 'overview' && (
        <div>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 80, color: 'var(--text-3)' }}>
              <div className="spinner" style={{ margin: '0 auto 16px', borderTopColor: 'var(--accent)', borderColor: 'var(--border)', width: 24, height: 24, borderWidth: 3 }} />
              Loading metrics…
            </div>
          ) : (
            <>
              {/* A — Model Performance */}
              <SectionLabel icon="📊" label="A — Model Performance" />
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 14, marginBottom: 14 }}>
                <div className="card" style={{ padding: '20px 22px' }}>
                  <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-3)', marginBottom: 8 }}>Current Fraud Rate</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <Gauge value={fraudRate} max={1} color={fraudRate > 0.3 ? 'var(--fraud)' : fraudRate > 0.1 ? '#f39c12' : 'var(--safe)'} />
                    <div>
                      <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>Threshold</div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)' }}>30% alert</div>
                    </div>
                  </div>
                  {h.fraud.length > 1 && <div style={{ marginTop: 8 }}><Sparkline data={h.fraud} color={fraudRate > 0.3 ? 'var(--fraud)' : 'var(--safe)'} /></div>}
                </div>
                <MetricCard label="Fraud Predictions" value={fmt(metrics?.predictions_fraud ?? 0)} sub="Flagged transactions" color="var(--fraud)" badge="FRAUD" badgeClass="badge-fraud" />
                <MetricCard label="Legitimate Predictions" value={fmt(metrics?.predictions_legit ?? 0)} sub="Clean transactions" color="var(--safe)" badge="LEGIT" badgeClass="badge-safe" />
                <MetricCard label="Total Predictions" value={fmt(totalPreds)} sub="All time" color="var(--accent)" />
                <MetricCard label="Prediction Errors" value={fmt(metrics?.prediction_errors ?? 0)} sub="API failures" color={metrics?.prediction_errors ? 'var(--fraud)' : 'var(--text-3)'} badge={metrics?.prediction_errors ? 'ERRORS' : 'OK'} badgeClass={metrics?.prediction_errors ? 'badge-fraud' : 'badge-safe'} />
              </div>

              {/* B — Model Serving Metadata */}
              <SectionLabel icon="🏷️" label="B — Model Serving Metadata" />
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 14, marginBottom: 14 }}>
                <div className="card" style={{ padding: '20px 22px' }}>
                  <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-3)', marginBottom: 10 }}>Model Status</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span className={`status-dot ${health?.model_loaded ? 'online' : ''}`} style={{ width: 10, height: 10 }} />
                    <span style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-1)' }}>{health?.model_loaded ? 'Loaded' : 'Not loaded'}</span>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 8 }}>{health?.status ?? '—'}</div>
                </div>
                <MetricCard label="Production Model" value={modelMeta?.model_name ?? '—'} sub={`v${modelMeta?.version ?? '?'} · ${modelMeta?.algorithm ?? ''}`} badge="PROD" badgeClass="badge-blue" />
                <MetricCard label="Features" value={(modelMeta?.features_count ?? 0).toString()} sub="Input features" color="var(--accent)" />
                <div className="card" style={{ padding: '20px 22px' }}>
                  <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-3)', marginBottom: 8 }}>Loaded At</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', fontFamily: 'var(--font-mono)' }}>{modelMeta?.loaded_at ? new Date(modelMeta.loaded_at).toLocaleString() : '—'}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>Run: {modelMeta?.mlflow_run_id?.substring(0, 12) ?? '—'}</div>
                </div>
              </div>

              {/* C — API Service Metrics */}
              <SectionLabel icon="⚡" label="C — API Service Metrics" />
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 14, marginBottom: 14 }}>
                <MetricCard label="Latency p50" value={msLabel(metrics?.prediction_latency_p50 ?? 0)} sub="Median response time" color="var(--accent)" sparkData={h.latency} />
                <MetricCard label="Latency p95" value={msLabel(metrics?.prediction_latency_p95 ?? 0)} sub="95th percentile" color="#f39c12" badge={metrics?.prediction_latency_p95 && metrics.prediction_latency_p95 > 0.5 ? 'SLOW' : 'OK'} badgeClass={metrics?.prediction_latency_p95 && metrics.prediction_latency_p95 > 0.5 ? 'badge-fraud' : 'badge-safe'} />
                <MetricCard label="Latency p99" value={msLabel(metrics?.prediction_latency_p99 ?? 0)} sub="99th percentile" color="var(--fraud)" />
                <MetricCard label="HTTP Requests" value={fmt(metrics?.http_requests_total ?? 0)} sub="Total requests served" color="var(--accent)" sparkData={h.reqs} />
              </div>

              {/* D — Infrastructure (Kubernetes) */}
              <SectionLabel icon="💻" label="D — Infrastructure (Kubernetes)" />
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 14, marginBottom: 14 }}>
                <MetricCard label="Running Pods" value={(metrics?.k8s_running_pods ?? 0).toString()} sub="fraud-detection ns" color="var(--safe)" badge={(metrics?.k8s_running_pods ?? 0) > 0 ? 'UP' : 'DOWN'} badgeClass={(metrics?.k8s_running_pods ?? 0) > 0 ? 'badge-safe' : 'badge-fraud'} />
                <MetricCard label="Pod Restarts" value={(metrics?.k8s_restart_pods ?? 0).toString()} sub="Total restarts" color={(metrics?.k8s_restart_pods ?? 0) > 5 ? 'var(--fraud)' : 'var(--safe)'} badge={(metrics?.k8s_restart_pods ?? 0) > 5 ? 'HIGH' : 'OK'} badgeClass={(metrics?.k8s_restart_pods ?? 0) > 5 ? 'badge-fraud' : 'badge-safe'} />
                <MetricCard label="Pending Pods" value={(metrics?.k8s_pending_pods ?? 0).toString()} sub="Waiting to start" color={(metrics?.k8s_pending_pods ?? 0) > 0 ? '#f39c12' : 'var(--text-3)'} />
                <MetricCard label="Failed Pods" value={(metrics?.k8s_failed_pods ?? 0).toString()} sub="Error state" color={(metrics?.k8s_failed_pods ?? 0) > 0 ? 'var(--fraud)' : 'var(--text-3)'} badge={(metrics?.k8s_failed_pods ?? 0) > 0 ? 'ALERT' : 'OK'} badgeClass={(metrics?.k8s_failed_pods ?? 0) > 0 ? 'badge-fraud' : 'badge-safe'} />
              </div>

              {/* CPU + Memory bars */}
              {(cpuPods.length > 0 || memPods.length > 0) && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
                  <div className="card" style={{ padding: '20px 22px' }}>
                    <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-3)', marginBottom: 16 }}>CPU Usage — fraud-detection Pods</div>
                    {cpuPods.map(([pod, val]) => (
                      <PodBar key={pod} label={pod} value={val} max={maxCpu} color="var(--accent)" />
                    ))}
                    {cpuPods.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-4)' }}>No data</div>}
                  </div>
                  <div className="card" style={{ padding: '20px 22px' }}>
                    <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-3)', marginBottom: 16 }}>Memory Usage — fraud-detection Pods</div>
                    {memPods.map(([pod, val]) => (
                      <PodBar key={pod} label={pod} value={val} max={maxMem} color="var(--safe)" />
                    ))}
                    {memPods.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-4)' }}>No data</div>}
                  </div>
                </div>
              )}

              {/* E — CI/CD & Drift Monitoring */}
              <SectionLabel icon="🔄" label="E — CI/CD & Drift Monitoring" />
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 14, marginBottom: 14 }}>
                <div className="card" style={{ padding: '20px 22px', background: isDrift ? 'var(--fraud-bg)' : 'var(--safe-bg)', borderColor: isDrift ? 'var(--fraud-border)' : 'var(--safe-border)' }}>
                  <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-3)', marginBottom: 10 }}>Drift Status</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontSize: 24 }}>{isDrift ? '🚨' : '✅'}</span>
                    <div>
                      <div style={{ fontSize: 20, fontWeight: 800, color: isDrift ? 'var(--fraud)' : 'var(--safe)' }}>{isDrift ? 'DRIFT' : 'STABLE'}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{driftStatus?.status}</div>
                    </div>
                  </div>
                </div>
                <div className="card" style={{ padding: '20px 22px' }}>
                  <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-3)', marginBottom: 8 }}>Drift Score</div>
                  <Gauge value={metrics?.drift_score ?? 0} max={1} color={(metrics?.drift_score ?? 0) > 0.3 ? 'var(--fraud)' : 'var(--safe)'} />
                </div>
                <MetricCard label="Drifted Features" value={(metrics?.drift_features_count ?? 0).toString()} sub="Features out of distribution" color={metrics?.drift_features_count ? 'var(--fraud)' : 'var(--safe)'} badge={metrics?.drift_features_count ? 'DRIFTED' : 'STABLE'} badgeClass={metrics?.drift_features_count ? 'badge-fraud' : 'badge-safe'} />
                <div className="card" style={{ padding: '20px 22px' }}>
                  <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-3)', marginBottom: 8 }}>Last Drift Check</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)', fontFamily: 'var(--font-mono)' }}>{driftStatus?.last_check ? new Date(driftStatus.last_check).toLocaleDateString() : 'No data'}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>{driftStatus?.last_check ? new Date(driftStatus.last_check).toLocaleTimeString() : 'Run Jenkins pipeline'}</div>
                  {driftStatus?.report_available && (
                    <button onClick={() => setActiveTab('report')} style={{ fontSize: 12, color: 'var(--accent)', fontWeight: 600, background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginTop: 8 }}>
                      View Evidently Report →
                    </button>
                  )}
                </div>
              </div>

              {!metrics && (
                <div className="alert alert-info" style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 8 }}>
                  <span>ℹ️</span>
                  <span>Live metrics require the <code style={{ fontFamily: 'var(--font-mono)', fontSize: 12, background: 'var(--accent-bg)', padding: '1px 6px', borderRadius: 4 }}>/metrics-summary</code> endpoint in your <code style={{ fontFamily: 'var(--font-mono)', fontSize: 12, background: 'var(--accent-bg)', padding: '1px 6px', borderRadius: 4 }}>api.py</code>.</span>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* TAB: EVIDENTLY REPORT */}
      {activeTab === 'report' && (
        <div className="card" style={{ overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10, background: 'var(--surface-2)' }}>
            <span style={{ fontSize: 16 }}>≋</span>
            <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-1)' }}>Evidently Drift Report</span>
            {!driftStatus?.report_available && <span className="badge badge-fraud" style={{ marginLeft: 'auto', fontSize: 10 }}>Not available — run Jenkins pipeline</span>}
          </div>
          <iframe src={`${API_URL}/drift-report`} width="100%" height={720} frameBorder="0" style={{ display: 'block' }} title="Evidently Drift Report" />
        </div>
      )}

    </div>
  );
}