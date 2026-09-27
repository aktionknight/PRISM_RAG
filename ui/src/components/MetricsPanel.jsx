import React, { useState, useEffect } from 'react';
import { Icon } from './Icons';

/**
 * MetricsPanel — Embeds Grafana dashboard and provides metrics overview.
 *
 * Two modes:
 * 1. Embedded Grafana iframe (when --profile obs is running)
 * 2. Real-time metrics from WebSocket telemetry (always available)
 */
export default function MetricsPanel({ telemetryData, sessionStats }) {
  const [grafanaAvailable, setGrafanaAvailable] = useState(false);
  const [showGrafana, setShowGrafana] = useState(false);

  useEffect(() => {
    // Check if Grafana is running
    fetch('http://localhost:3000/api/health', { mode: 'no-cors' })
      .then(() => setGrafanaAvailable(true))
      .catch(() => setGrafanaAvailable(false));
  }, []);

  const metrics = telemetryData || {};
  const stats = sessionStats || {};

  // Calculate derived metrics
  const avgControllerLatency = metrics.controllerLatencies?.length > 0
    ? (metrics.controllerLatencies.reduce((a, b) => a + b, 0) / metrics.controllerLatencies.length).toFixed(1)
    : '—';

  const avgRetrievalLatency = metrics.retrievalLatencies?.length > 0
    ? (metrics.retrievalLatencies.reduce((a, b) => a + b, 0) / metrics.retrievalLatencies.length).toFixed(1)
    : '—';

  const earlyRetrievalRate = metrics.totalChunks > 0
    ? ((metrics.earlyRetrievals / metrics.totalChunks) * 100).toFixed(1)
    : '0.0';

  const citationSupportRate = stats.claimCount > 0
    ? ((stats.citationsCount / stats.claimCount) * 100).toFixed(1)
    : '100';

  // Gate status
  const g2Pass = metrics.earlyRetrievals > 0;
  const g3Pass = stats.intentCount > 0;
  const g4Pass = stats.citationsCount > 0 && metrics.fabricatedIds === 0;
  const g5Pass = stats.answerVersion >= 1;
  const g6Pass = metrics.traceCoverage >= 0.95;

  if (showGrafana && grafanaAvailable) {
    return (
      <div className="grafana-view">
        <div className="grafana-toolbar">
          <h3 className="grafana-title">
            <Icon name="dashboard" size={15} /> Grafana Dashboard
          </h3>
          <button className="btn-mini" onClick={() => setShowGrafana(false)}>
            <Icon name="arrowLeft" size={12} /> Back to Metrics
          </button>
        </div>
        <iframe
          src="http://localhost:3000/d/slrag-main/slrag-streaming-live-rag?orgId=1&refresh=5s&kiosk"
          className="grafana-frame"
          title="Grafana Dashboard"
        />
      </div>
    );
  }

  return (
    <div className="metrics-scroll">
      {/* Header with Grafana button */}
      <div className="metrics-toolbar">
        <h3 className="metrics-heading">
          <Icon name="trend" size={15} /> Live Metrics
        </h3>
        {grafanaAvailable && (
          <button className="btn-mini btn-mini-accent" onClick={() => setShowGrafana(true)}>
            <Icon name="dashboard" size={12} /> Open Grafana
          </button>
        )}
      </div>

      {/* Gate Readouts — G1-G6 */}
      <MetricCard title="Gate Readouts" icon="target">
        <GateItem label="G2 Early Retrieval" pass={g2Pass} value={`${earlyRetrievalRate}%`} />
        <GateItem label="G3 Intent Decomposition" pass={g3Pass} value={`${stats.intentCount || 0} intents`} />
        <GateItem label="G4 Citation Support" pass={g4Pass} value={`${citationSupportRate}%`} />
        <GateItem label="G5 Session State" pass={g5Pass} value={`V${stats.answerVersion || 0}`} />
        <GateItem label="G6 Trace Coverage" pass={g6Pass} value={`${((metrics.traceCoverage || 0) * 100).toFixed(1)}%`} />
        <InfoRow label="Fabricated IDs" monoValue={
          <span className={metrics.fabricatedIds === 0 ? 'gate-pass' : 'gate-fail'}>
            {metrics.fabricatedIds || 0}
          </span>
        } />
      </MetricCard>

      {/* Performance Budget — HC-5 */}
      <MetricCard title="Performance Budget (HC-5)" icon="gauge">
        <MetricRow
          label="Controller Latency (p95)"
          value={`${avgControllerLatency} ms`}
          target="≤15ms"
          status={parseFloat(avgControllerLatency) <= 15 ? 'pass' : 'warn'}
        />
        <MetricRow
          label="Retrieval Latency"
          value={`${avgRetrievalLatency} ms`}
          target="≤60ms"
          status={parseFloat(avgRetrievalLatency) <= 60 ? 'pass' : 'warn'}
        />
        <MetricRow
          label="LLM Calls per Turn"
          value={`${stats.llmCallsThisTurn || 0}`}
          target="≤3"
          status={(stats.llmCallsThisTurn || 0) <= 3 ? 'pass' : 'fail'}
        />
      </MetricCard>

      {/* Pipeline Statistics */}
      <MetricCard title="Pipeline Statistics" icon="chart">
        <StatGrid>
          <StatItem label="Retrievals" value={stats.retrievalCount || 0} color="green" />
          <StatItem label="Sub-Intents" value={stats.intentCount || 0} color="indigo" />
          <StatItem label="Claims" value={stats.claimCount || 0} color="cyan" />
          <StatItem label="Events" value={stats.telemetryEventCount || 0} color="amber" />
        </StatGrid>
      </MetricCard>

      {/* Token & Cost Tracking */}
      <MetricCard title="Token & Cost" icon="wallet">
        <div className="stat-grid">
          <StatItem label="Prompt Tokens" value={stats.totalTokensPrompt || 0} color="" />
          <StatItem label="Completion Tokens" value={stats.totalTokensCompletion || 0} color="" />
        </div>
        <InfoRow label="Total Cost" monoValue={
          <span className="cost-value">${(stats.totalCost || 0).toFixed(4)}</span>
        } />
      </MetricCard>

      {/* Session Info */}
      <MetricCard title="Session Info" icon="settings">
        <InfoRow label="Session ID" value={stats.sessionId || '—'} />
        <InfoRow label="Turn ID" value={stats.turnId || 0} />
        <InfoRow label="Answer Version" value={`V${stats.answerVersion || 0}`} />
        <InfoRow label="Active Time" value={formatUptime(stats.sessionStartTime)} />
      </MetricCard>

      {/* Grafana Status */}
      {!grafanaAvailable && (
        <div className="grafana-hint">
          <div className="grafana-hint-title">
            <Icon name="warning" size={12} /> Grafana Not Running
          </div>
          Start with: <code>docker compose --profile obs up</code>
        </div>
      )}
    </div>
  );
}

// Helper Components
function MetricCard({ title, icon, children }) {
  return (
    <div className="telemetry-card">
      <div className="telemetry-card-title">
        <Icon name={icon} size={12} /> {title}
      </div>
      {children}
    </div>
  );
}

function GateItem({ label, pass, value }) {
  return (
    <div className="metric-row">
      <span className="metric-label">{label}</span>
      <div className="metric-right">
        <span className="metric-value">{value}</span>
        <span className={`gate-pill ${pass ? 'gate-pill-pass' : ''}`}>
          {pass ? <><Icon name="check" size={9} strokeWidth={3} /> PASS</> : '—'}
        </span>
      </div>
    </div>
  );
}

function MetricRow({ label, value, target, status }) {
  const colors = {
    pass: 'gate-pass',
    warn: 'gate-warn',
    fail: 'gate-fail',
  };
  return (
    <div className="metric-row">
      <div className="metric-label">
        {label}
        <span className="metric-target">target: {target}</span>
      </div>
      <span className={`metric-strong ${colors[status] || ''}`}>{value}</span>
    </div>
  );
}

function StatGrid({ children }) {
  return (
    <div className="stat-grid">{children}</div>
  );
}

function StatItem({ label, value, color }) {
  return (
    <div className="stat-tile">
      <div className={`stat-big ${color || ''}`}>{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

function InfoRow({ label, value, monoValue }) {
  return (
    <div className="metric-row">
      <span className="metric-label">{label}</span>
      <span className="metric-mono">
        {monoValue || value}
      </span>
    </div>
  );
}

function formatUptime(startTime) {
  if (!startTime) return '—';
  const elapsed = Math.floor((Date.now() - startTime) / 1000);
  if (elapsed < 60) return `${elapsed}s`;
  if (elapsed < 3600) return `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`;
  return `${Math.floor(elapsed / 3600)}h ${Math.floor((elapsed % 3600) / 60)}m`;
}
