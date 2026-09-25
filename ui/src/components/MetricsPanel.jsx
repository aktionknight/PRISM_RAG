import React, { useState, useEffect } from 'react';

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
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '12px 16px',
          background: 'var(--bg-secondary)',
          borderBottom: '1px solid var(--border-glass)',
        }}>
          <h3 style={{ fontSize: '14px', fontWeight: 600, margin: 0 }}>
            📊 Grafana Dashboard
          </h3>
          <button
            onClick={() => setShowGrafana(false)}
            style={{
              background: 'var(--bg-glass)',
              border: '1px solid var(--border-glass)',
              color: 'var(--text-secondary)',
              padding: '4px 12px',
              borderRadius: '6px',
              fontSize: '12px',
              cursor: 'pointer',
            }}
          >
            ← Back to Metrics
          </button>
        </div>
        <iframe
          src="http://localhost:3000/d/slrag-main/slrag-streaming-live-rag?orgId=1&refresh=5s&kiosk"
          style={{
            width: '100%',
            height: '100%',
            border: 'none',
            background: '#000',
          }}
          title="Grafana Dashboard"
        />
      </div>
    );
  }

  return (
    <div style={{
      height: '100%',
      overflowY: 'auto',
      padding: '16px',
    }}>
      {/* Header with Grafana button */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '16px',
      }}>
        <h3 style={{ fontSize: '14px', fontWeight: 600, margin: 0 }}>
          📈 Live Metrics
        </h3>
        {grafanaAvailable && (
          <button
            onClick={() => setShowGrafana(true)}
            style={{
              background: 'var(--gradient-primary)',
              border: 'none',
              color: 'white',
              padding: '6px 14px',
              borderRadius: '8px',
              fontSize: '11px',
              fontWeight: 600,
              cursor: 'pointer',
              boxShadow: 'var(--shadow-glow)',
            }}
          >
            📊 Open Grafana
          </button>
        )}
      </div>

      {/* Gate Readouts — G1-G6 */}
      <MetricCard title="🎯 Gate Readouts">
        <GateItem label="G2 Early Retrieval" pass={g2Pass} value={`${earlyRetrievalRate}%`} />
        <GateItem label="G3 Intent Decomposition" pass={g3Pass} value={`${stats.intentCount || 0} intents`} />
        <GateItem label="G4 Citation Support" pass={g4Pass} value={`${citationSupportRate}%`} />
        <GateItem label="G5 Session State" pass={g5Pass} value={`V${stats.answerVersion || 0}`} />
        <GateItem label="G6 Trace Coverage" pass={g6Pass} value={`${((metrics.traceCoverage || 0) * 100).toFixed(1)}%`} />
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '8px 0',
          borderBottom: '1px solid rgba(255,255,255,0.05)',
        }}>
          <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>Fabricated IDs</span>
          <span style={{
            fontSize: '13px',
            fontWeight: 700,
            color: (metrics.fabricatedIds || 0) === 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)',
          }}>
            {metrics.fabricatedIds || 0}
          </span>
        </div>
      </MetricCard>

      {/* Performance Budget — HC-5 */}
      <MetricCard title="⚡ Performance Budget (HC-5)">
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
      <MetricCard title="📊 Pipeline Statistics">
        <StatGrid>
          <StatItem label="Retrievals" value={stats.retrievalCount || 0} color="emerald" />
          <StatItem label="Sub-Intents" value={stats.intentCount || 0} color="indigo" />
          <StatItem label="Claims" value={stats.claimCount || 0} color="cyan" />
          <StatItem label="Events" value={stats.telemetryEventCount || 0} color="violet" />
        </StatGrid>
      </MetricCard>

      {/* Token & Cost Tracking */}
      <MetricCard title="💰 Token & Cost">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          <div>
            <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginBottom: '4px' }}>
              Prompt Tokens
            </div>
            <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)' }}>
              {stats.totalTokensPrompt || 0}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginBottom: '4px' }}>
              Completion Tokens
            </div>
            <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)' }}>
              {stats.totalTokensCompletion || 0}
            </div>
          </div>
        </div>
        <div style={{
          marginTop: '12px',
          paddingTop: '12px',
          borderTop: '1px solid rgba(255,255,255,0.05)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>Total Cost</span>
          <span style={{ fontSize: '20px', fontWeight: 700, color: 'var(--accent-emerald)' }}>
            ${(stats.totalCost || 0).toFixed(4)}
          </span>
        </div>
      </MetricCard>

      {/* Session Info */}
      <MetricCard title="🔧 Session Info">
        <InfoRow label="Session ID" value={stats.sessionId || '—'} />
        <InfoRow label="Turn ID" value={stats.turnId || 0} />
        <InfoRow label="Answer Version" value={`V${stats.answerVersion || 0}`} />
        <InfoRow label="Active Time" value={formatUptime(stats.sessionStartTime)} />
      </MetricCard>

      {/* Grafana Status */}
      {!grafanaAvailable && (
        <div style={{
          marginTop: '16px',
          padding: '12px',
          background: 'rgba(245, 158, 11, 0.1)',
          border: '1px solid rgba(245, 158, 11, 0.3)',
          borderRadius: '8px',
          fontSize: '11px',
          color: 'var(--accent-amber)',
        }}>
          <strong>⚠️ Grafana Not Running</strong><br />
          Start with: <code style={{
            background: 'rgba(0,0,0,0.3)',
            padding: '2px 6px',
            borderRadius: '4px',
            fontFamily: 'var(--font-mono)',
          }}>docker compose --profile obs up</code>
        </div>
      )}
    </div>
  );
}

// Helper Components
function MetricCard({ title, children }) {
  return (
    <div style={{
      background: 'var(--bg-glass)',
      border: '1px solid var(--border-glass)',
      borderRadius: 'var(--radius-sm)',
      padding: '12px',
      marginBottom: '12px',
    }}>
      <div style={{
        fontSize: '11px',
        fontWeight: 600,
        color: 'var(--text-secondary)',
        marginBottom: '10px',
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
      }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function GateItem({ label, pass, value }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: '8px 0',
      borderBottom: '1px solid rgba(255,255,255,0.05)',
    }}>
      <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>{label}</span>
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{value}</span>
        <span style={{
          fontSize: '10px',
          fontWeight: 700,
          padding: '3px 8px',
          borderRadius: '4px',
          background: pass ? 'rgba(16, 185, 129, 0.15)' : 'rgba(148, 163, 184, 0.15)',
          color: pass ? 'var(--accent-emerald)' : 'var(--text-dim)',
        }}>
          {pass ? '✓ PASS' : '—'}
        </span>
      </div>
    </div>
  );
}

function MetricRow({ label, value, target, status }) {
  const colors = {
    pass: 'var(--accent-emerald)',
    warn: 'var(--accent-amber)',
    fail: 'var(--accent-rose)',
  };
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: '8px 0',
      borderBottom: '1px solid rgba(255,255,255,0.05)',
    }}>
      <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
        {label}
        <span style={{ fontSize: '9px', marginLeft: '6px', opacity: 0.6 }}>target: {target}</span>
      </div>
      <span style={{ fontSize: '13px', fontWeight: 700, color: colors[status] || 'var(--text-primary)' }}>
        {value}
      </span>
    </div>
  );
}

function StatGrid({ children }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
      {children}
    </div>
  );
}

function StatItem({ label, value, color }) {
  const colors = {
    emerald: 'var(--accent-emerald)',
    indigo: 'var(--accent-indigo)',
    cyan: 'var(--accent-cyan)',
    violet: 'var(--accent-violet)',
    amber: 'var(--accent-amber)',
  };
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: '24px', fontWeight: 700, color: colors[color] || 'var(--text-primary)' }}>
        {value}
      </div>
      <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '4px' }}>
        {label}
      </div>
    </div>
  );
}

function InfoRow({ label, value }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      padding: '6px 0',
      fontSize: '11px',
      borderBottom: '1px solid rgba(255,255,255,0.05)',
    }}>
      <span style={{ color: 'var(--text-dim)' }}>{label}</span>
      <span style={{
        color: 'var(--text-primary)',
        fontFamily: 'var(--font-mono)',
        fontSize: '10px',
      }}>
        {value}
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
