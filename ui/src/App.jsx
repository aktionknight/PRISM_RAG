import React, { useState, useEffect, useRef } from 'react';
import './index.css';
import MetricsPanel from './components/MetricsPanel';
import { Icon } from './components/Icons';

const STATUS_CONNECTED = 'Connected';
const STATUS_DISCONNECTED = 'Disconnected';
const STATUS_ERROR = 'Error';
const STATUS_CONNECTING = 'Connecting…';

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/[&<>'"]/g,
    tag => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[tag] || tag)
  );
}

export default function App() {
  const [isPreloading, setIsPreloading] = useState(true);
  const [status, setStatus] = useState(STATUS_CONNECTING);
  const [sessionId, setSessionId] = useState('—');
  const [chunks, setChunks] = useState([]);
  const [subQueries, setSubQueries] = useState([]);
  const [retrievals, setRetrievals] = useState([]);
  const [streamingTokens, setStreamingTokens] = useState([]);
  const [finalAnswer, setFinalAnswer] = useState(null);
  const [citations, setCitations] = useState([]);
  const [uncertainties, setUncertainties] = useState([]);
  const [pipelineStatus, setPipelineStatus] = useState('');
  const [history, setHistory] = useState([]);

  const [stats, setStats] = useState({
    retrievalCount: 0,
    intentCount: 0,
    claimCount: 0,
    telemetryEventCount: 0,
    latencies: [],
    totalTokens: 0,
    totalCost: 0,
    answerVersion: 0,
    sessionId: '—',
    turnId: 0,
    totalTokensPrompt: 0,
    totalTokensCompletion: 0,
    citationsCount: 0,
    llmCallsThisTurn: 0,
    sessionStartTime: null,
  });

  const [telemetryData, setTelemetryData] = useState({
    controllerLatencies: [],
    retrievalLatencies: [],
    earlyRetrievals: 0,
    totalChunks: 0,
    fabricatedIds: 0,
    traceCoverage: 1.0,
  });

  const [inputVal, setInputVal] = useState('');
  const [corpusDocs, setCorpusDocs] = useState([]);
  const [isUploading, setIsUploading] = useState(false);
  const [toast, setToast] = useState(null);

  const wsRef = useRef(null);
  const fileInputRef = useRef(null);
  const toastTimerRef = useRef(null);


  const streamPaneRef = useRef(null);
  const answerPaneRef = useRef(null);

  // Toast helper
  const showToast = (message, type = 'info') => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToast({ message, type });
    toastTimerRef.current = setTimeout(() => setToast(null), 3500);
  };

  // Fetch corpus documents
  const fetchCorpusDocs = async () => {
    try {
      const res = await fetch('/api/corpus/documents');
      if (res.ok) {
        const data = await res.json();
        setCorpusDocs(data.documents || []);
      }
    } catch (e) {
      console.warn('Failed to fetch corpus documents:', e);
    }
  };

  useEffect(() => {
    fetchCorpusDocs();
  }, []);

  // Auto-scroll panes
  useEffect(() => {

    if (streamPaneRef.current) {
      streamPaneRef.current.scrollTop = streamPaneRef.current.scrollHeight;
    }
  }, [chunks]);

  useEffect(() => {
    if (answerPaneRef.current) {
      answerPaneRef.current.scrollTop = answerPaneRef.current.scrollHeight;
    }
  }, [streamingTokens, finalAnswer, subQueries, uncertainties]);

  // Preload models before connecting
  useEffect(() => {
    fetch('/api/preload')
      .then(res => res.json())
      .then(data => {
        console[data.status === 'ok' ? 'log' : 'error']('Model preload:', data);
        setIsPreloading(false);
      })
      .catch(err => {
        console.error('Preload failed:', err);
        setIsPreloading(false); // allow app to load anyway
      });
  }, []);

  useEffect(() => {
    if (isPreloading) return;
    connect();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [isPreloading]);

  const connect = () => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const ws = new WebSocket(`${protocol}//${host}/ws/session`);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus(STATUS_CONNECTED);
    };

    ws.onclose = () => {
      setStatus(STATUS_DISCONNECTED);
      setTimeout(connect, 2000);
    };

    ws.onerror = () => {
      setStatus(STATUS_ERROR);
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      handleMessage(msg);
    };
  };

  const handleMessage = (msg) => {
    switch (msg.type) {
      case 'session_created':
        setSessionId(msg.session_id);
        setStats(s => ({ ...s, sessionId: msg.session_id, sessionStartTime: Date.now() }));
        break;

      case 'controller_decision':
        setChunks(prev => [...prev, msg]);
        if (msg.latency_ms) {
          setStats(s => ({ ...s, latencies: [...s.latencies, msg.latency_ms] }));
          setTelemetryData(t => ({
            ...t,
            controllerLatencies: [...t.controllerLatencies.slice(-50), msg.latency_ms],
            totalChunks: t.totalChunks + 1,
            earlyRetrievals: msg.decision === 'RETRIEVE' ? t.earlyRetrievals + 1 : t.earlyRetrievals,
          }));
        }
        break;

      case 'subqueries_updated':
        setSubQueries(msg.sub_queries || []);
        setStats(s => ({
          ...s,
          intentCount: msg.total_intents || (msg.sub_queries || []).length,
          novelIntents: (msg.new_intents || []).length,
        }));
        break;

      case 'retrieval_complete':
        setRetrievals(msg.events || []);
        setStats(s => ({ ...s, retrievalCount: (msg.events || []).length }));
        break;

      case 'answer_token':
        setStreamingTokens(prev => {
          const next = [...prev];
          const existingIdx = next.findIndex(t => t.seq === msg.seq);
          if (existingIdx >= 0) {
            next[existingIdx] = msg;
          } else {
            next.push(msg);
          }
          return next;
        });
        break;

      case 'pipeline_status':
        setPipelineStatus(msg.message || '');
        break;

      case 'answer_version': {
        setSubQueries(msg.sub_queries || []);
        const diagnostic = msg.llm_diagnostics;
        if (diagnostic) {
          setPipelineStatus(msg.suppression ? 'Previous answer reformatted; retrieval suppressed' : diagnostic.error ? `LLM failed: ${diagnostic.error}` :
            diagnostic.calls === 0 ? `LLM skipped: ${diagnostic.context_chunks} grounding chunks` :
            `LLM completed: ${diagnostic.calls} call(s), ${(msg.claims || []).length} verified claims, ${diagnostic.parse_errors} parse errors`);
        }
        setStreamingTokens([]);
        setHistory(prev => [
            ...prev,
            {
              type: 'agent',
              answer: msg.answer || '',
              version: msg.version ?? 0,
              turn_id: msg.turn_id || 1,
              claims: msg.claims || [],
              citations: msg.citations || [],
            }
          ]);
        setFinalAnswer({
          version: msg.version ?? 0,
          turn_id: msg.turn_id || 1,
          answer: msg.answer || '',
        });
        setCitations(msg.citations || []);
        // Extract telemetry data from synthesis result
        const tel = msg.telemetry || {};
        setStats(s => ({
          ...s,
          answerVersion: msg.version ?? 0,
          turnId: msg.turn_id || 1,
          claimCount: (msg.claims || []).length,
          citationsCount: (msg.citations || []).length,
          totalTokens: (tel.total_tokens_prompt || 0) + (tel.total_tokens_completion || 0),
          totalTokensPrompt: tel.total_tokens_prompt || s.totalTokensPrompt,
          totalTokensCompletion: tel.total_tokens_completion || s.totalTokensCompletion,
          totalCost: tel.total_cost_usd || s.totalCost,
          synthesisLatency: tel.synthesis_latency_ms || 0,
          llmCallsThisTurn: tel.llm_calls || 0,
        }));
        break;
      }

      case 'uncertainty':
        if (msg.text) {
          setUncertainties(prev => [...prev, msg.text]);
        }
        break;

      case 'telemetry_tick':
        setStats(s => {
          const nextS = { ...s, telemetryEventCount: s.telemetryEventCount + 1 };
          if (msg.latency_ms) {
            nextS.latencies = [...s.latencies, msg.latency_ms];
          }
          return nextS;
        });
        break;

      default:
        break;
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    showToast(`Uploading and indexing "${file.name}"…`, 'info');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/api/corpus/upload', {
        method: 'POST',
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        setCorpusDocs(data.documents || []);
        showToast(`"${file.name}" indexed successfully!`, 'success');
      } else {
        const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
        showToast(`Upload failed: ${err.detail || 'Server error'}`, 'warn');
      }
    } catch (err) {
      showToast(`Upload failed: ${err.message}`, 'warn');
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const resetSession = async () => {
    try {
      const res = await fetch('/api/corpus/reset', { method: 'POST' });
      if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(error.detail || `Server returned ${res.status}`);
      }
      const data = await res.json();
      setCorpusDocs(data.documents || []);
    } catch (e) {
      console.warn('Corpus reset endpoint failed:', e);
      showToast(`Reset failed: ${e.message}`, 'warn');
      await fetchCorpusDocs();
      return;
    }

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'new_session' }));
    }
    setChunks([]);
    setSubQueries([]);
    setRetrievals([]);
    setStreamingTokens([]);
    setFinalAnswer(null);
    setCitations([]);
    setUncertainties([]);
    setHistory([]);
    setStats({
      retrievalCount: 0,
      intentCount: 0,
      claimCount: 0,
      telemetryEventCount: 0,
      latencies: [],
      totalTokens: 0,
      totalCost: 0,
      answerVersion: 0,
      sessionId: '—',
      turnId: 0,
      totalTokensPrompt: 0,
      totalTokensCompletion: 0,
      citationsCount: 0,
      llmCallsThisTurn: 0,
      sessionStartTime: Date.now(),
    });
    setTelemetryData({
      controllerLatencies: [],
      retrievalLatencies: [],
      earlyRetrievals: 0,
      totalChunks: 0,
      fabricatedIds: 0,
      traceCoverage: 1.0,
    });
    showToast('Custom uploads and sessions reset. Permanent test document retained.', 'success');
  };


  const sendQuery = () => {
    const text = inputVal.trim();
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    setInputVal('');
    setUncertainties([]);
    setSubQueries([]);
    setStreamingTokens([]);
    setPipelineStatus('Processing query…');
    setHistory(prev => [...prev, { type: 'user', text }]);

    // Simulate streaming chunks
    const words = text.split(/\s+/);
    const chunkSize = Math.max(3, Math.ceil(words.length / 4));
    const chunksToSend = [];
    for (let i = 0; i < words.length; i += chunkSize) {
      chunksToSend.push(words.slice(i, i + chunkSize).join(' '));
    }

    let delay = 0;
    chunksToSend.forEach((chunkText, idx) => {
      setTimeout(() => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({
            type: 'chunk',
            t_s: parseFloat((idx * 0.8).toFixed(1)),
            text: chunkText + ' ',
            is_final: idx === chunksToSend.length - 1,
          }));
        }
      }, delay);
      delay += 600;
    });

    setTimeout(() => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'utterance_end' }));
      }
    }, delay + 200);
  };

  const runDemo = () => {
    const demoText = "I need a large meeting room that can accommodate about 30 people, and also tell me about the cancellation policy and what catering options are available";
    setInputVal(demoText);
    setTimeout(() => {
      // Small hack to ensure state updates before send
      document.getElementById('sendBtn').click();
    }, 100);
  };

  // Derived stats
  const avgLatency = stats.latencies.length > 0
    ? (stats.latencies.reduce((a,b)=>a+b,0) / stats.latencies.length).toFixed(1)
    : '—';

  return (
    <>
      {isPreloading && (
        <div className="loading-overlay fade-in">
          <div className="spinner"></div>
          <div className="loading-text">Warming up Embedding &amp; NLP Models…</div>
        </div>
      )}
      <header className="header">
        <div className="header-left">
          <div>
            <div className="logo">PRISM</div>
            <div className="logo-sub">Streaming Live RAG Engine</div>
          </div>
        </div>
        <div className="header-right">
          <div
            className="corpus-badge"
            title={`Corpus: ${corpusDocs.map(d => d.name + (d.is_permanent ? ' (permanent)' : d.is_sample ? ' (sample)' : '')).join(', ')}`}
          >
            <Icon name="file" size={12} />
            <span>{corpusDocs.length} Doc{corpusDocs.length === 1 ? '' : 's'}</span>
          </div>
          <div className={`status-dot ${status === STATUS_CONNECTED ? '' : 'disconnected'}`}></div>
          <span className="status-text">{status}</span>
          <span className="session-id">{sessionId}</span>
        </div>

      </header>

      <main className="main">
        {/* Left Pane: Live Stream */}
        <div className="pane">
          <div className="pane-header">
            <span className="pane-title"><Icon name="signal" size={14} /> Live Stream</span>
            <span className="pane-badge">{chunks.length} chunks</span>
          </div>
          <div className="pane-body" ref={streamPaneRef}>
            {chunks.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon"><Icon name="signal" size={20} strokeWidth={1.5} /></div>
                <div className="empty-state-text">Waiting for transcript chunks…</div>
              </div>
            ) : (
              chunks.map((msg, i) => {
                const decision = msg.decision;
                let badgeClass = 'badge-wait';
                let badgeText = 'WAIT';
                let badgeIcon = null;
                if (decision === 'RETRIEVE') { badgeClass = 'badge-retrieve'; badgeText = 'RETRIEVE'; badgeIcon = 'bolt'; }
                else if (decision === 'NO_RETRIEVAL') { badgeClass = 'badge-suppress'; badgeText = 'SUPPRESS'; badgeIcon = 'stop'; }

                const conf = msg.confidence || 0;
                const confPct = Math.round(conf * 100);
                const confColor = conf > 0.7 ? 'var(--accent-emerald)' : conf > 0.4 ? 'var(--accent-amber)' : 'var(--accent-rose)';

                return (
                  <div key={i} className="chunk-item">
                    <div className="chunk-time">{(msg.t_s || 0).toFixed(1)}s</div>
                    <div className="chunk-content">
                      <div className="chunk-text">{msg.prefix || ''}</div>
                      <div className="chunk-meta-row">
                        <span className={`chunk-badge ${badgeClass}`}>
                          {badgeIcon && <Icon name={badgeIcon} size={10} strokeWidth={2.5} />}
                          {badgeText}
                        </span>
                        {msg.stage_name && (
                          <span className="chunk-stage-badge" title={`Decided by: ${msg.stage_name}`}>
                            {msg.stage_name}
                          </span>
                        )}
                        <span className="chunk-reason">{msg.reason || ''}</span>
                        <span className="confidence-bar">
                          <span className="confidence-fill" style={{width: `${confPct}%`, background: confColor}}></span>
                        </span>
                      </div>
                      {(msg.margin !== undefined && msg.margin !== null ||
                        msg.entropy !== undefined && msg.entropy !== null ||
                        msg.threshold !== undefined && msg.threshold !== null) && (
                        <div className="chunk-metrics">
                          {msg.margin !== undefined && msg.margin !== null && (
                            <span className="chunk-metric-pill" title="Decision Margin / Content Anchor Count">
                              margin: {typeof msg.margin === 'number' ? msg.margin.toFixed(3) : msg.margin}
                            </span>
                          )}
                          {msg.entropy !== undefined && msg.entropy !== null && (
                            <span className="chunk-metric-pill" title="Normalized Score Entropy (H_norm)">
                              entropy: {typeof msg.entropy === 'number' ? msg.entropy.toFixed(3) : msg.entropy}
                            </span>
                          )}
                          {msg.threshold !== undefined && msg.threshold !== null && (
                            <span className="chunk-metric-pill" title="Active Stage Threshold">
                              threshold: {typeof msg.threshold === 'number' ? msg.threshold.toFixed(3) : msg.threshold}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Center Pane: Answer */}
        <div className="pane">
          <div className="pane-header">
            <span className="pane-title"><Icon name="message" size={14} /> Answer</span>
            <span className="pane-badge">V{stats.answerVersion}</span>
          </div>
          <div className="pane-body" ref={answerPaneRef}>
            {history.length === 0 && streamingTokens.length === 0 && !finalAnswer && subQueries.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon"><Icon name="message" size={20} strokeWidth={1.5} /></div>
                <div className="empty-state-text">Ask a question to see the grounded answer</div>
              </div>
            ) : (
              <div className="chat-history">
                {history.map((item, idx) => (
                  <div key={idx} className={`chat-message ${item.type}`}>
                    {item.type === 'user' ? (
                      <div className="user-message">
                        {item.text}
                      </div>
                    ) : (
                      <div className="agent-message">
                        <div className="version-info">
                          <span className="version-badge">V{item.version || 1}</span>
                          <span>Turn {item.turn_id}</span>
                          <span>•</span>
                          <span>{(item.citations || []).length} citations</span>
                        </div>
                        {item.claims && item.claims.length > 0 && (
                          <details className="sub-intents-container">
                            <summary>Verified supporting claims</summary>
                            {item.claims.map((claim, i) => (
                              <div key={i} className="sub-intent-item fade-in">
                                <span className="sub-intent-text">{claim.text}</span>
                                {(claim.citations || []).map((c, j) => (
                                  <span key={j} className="citation-chip">{c}</span>
                                ))}
                              </div>
                            ))}
                          </details>
                        )}
                        
                        {item.answer && (
                          <div className="answer-section fade-in" style={{ marginTop: '16px' }}>
                            <div
                              className="answer-sentence committed"
                              style={{ whiteSpace: 'pre-wrap' }}
                              dangerouslySetInnerHTML={{
                                __html: escapeHtml(item.answer).replace(/\[([^\]]+§[^\]]+)\]/g, '<span class="citation-chip">$1</span>')
                              }}
                            />
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}

                {(history.length > 0 && history[history.length - 1].type === 'user') && (
                  <div className="chat-message agent streaming">
                    {subQueries.length > 0 && (
                      <div className="sub-queries-box">
                        {subQueries.map((q, i) => (
                          <span key={i} className="sub-query-tag">{q}</span>
                        ))}
                      </div>
                    )}
                    {streamingTokens.length > 0 && (
                      <div className="sub-intents-container streaming">
                        {streamingTokens.map((t, i) => (
                          <div key={i} className={`sub-intent-item ${t.kind || 'provisional'} fade-in`}>
                            <span className="sub-intent-text">{t.text || ''}</span>
                            {(t.citations || []).map((c, j) => (
                              <span key={j} className="citation-chip" title={c}>{c}</span>
                            ))}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                
                {pipelineStatus && <div className="uncertainty-box"><span>{pipelineStatus}</span></div>}
                {uncertainties.map((u, i) => (
                  <div key={i} className="uncertainty-box fade-in">
                    <span className="uncertainty-icon"><Icon name="warning" size={13} /></span>
                    <span>{u}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Split into Top Box (Metrics) & Bottom Box (Intents Retrieval Timeline) */}
        <div className="pane-column">
          {/* Top Box: Metrics & Telemetry */}
          <div className="pane pane-metrics">
            <div className="pane-header">
              <span className="pane-title"><Icon name="gauge" size={14} /> Metrics &amp; Telemetry</span>
              <span className="pane-badge">{stats.telemetryEventCount} events</span>
            </div>
            <div className="pane-body pane-body-metrics">
              <MetricsPanel telemetryData={telemetryData} sessionStats={stats} />
            </div>
          </div>

          {/* Bottom Box: Intents Retrieval Timeline */}
          <div className="pane pane-timeline">
            <div className="pane-header">
              <span className="pane-title"><Icon name="clock" size={14} /> Retrieval Timeline</span>
              <span className="pane-badge">{retrievals.length} {retrievals.length === 1 ? 'query' : 'queries'}</span>
            </div>
            <div className="pane-body pane-body-timeline">
              {retrievals.length === 0 ? (
                <div className="timeline-empty-state">
                  <div className="empty-state-icon"><Icon name="clock" size={18} strokeWidth={1.5} /></div>
                  <div className="empty-state-text">No sub-intent retrievals yet</div>
                </div>
              ) : (() => {
                const maxTs = Math.max(...retrievals.map(e => e.timestamp_s || 0), 1);
                return (
                  <div className="timeline-list">
                    {retrievals.map((ev, idx) => {
                      const left = ((ev.timestamp_s || 0) / (maxTs + 0.5)) * 100;
                      const width = Math.max(15, 100 - left);
                      const isSpec = ev.trigger === 'provisional';
                      return (
                        <div key={idx} className="gantt-bar">
                          <span className="gantt-label" title={ev.query || ''}>{ev.facet || ev.query || `Q${idx + 1}`}</span>
                          <div className="gantt-track">
                            <div className={`gantt-fill ${isSpec ? 'speculative' : 'confirmed'}`} style={{left:`${left}%`, width:`${width}%`}}></div>
                          </div>
                          <span className="gantt-time">{(ev.timestamp_s || 0).toFixed(1)}s</span>
                        </div>
                      );
                    })}
                  </div>
                );
              })()}
            </div>
          </div>
        </div>
      </main>

      <div className="input-bar">
        <input
          className="input-field"
          type="text"
          placeholder="Type your query here… (streamed as chunks)"
          value={inputVal}
          onChange={e => setInputVal(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && sendQuery()}
          disabled={isUploading}
        />
        <button id="sendBtn" className="btn btn-primary" onClick={sendQuery} disabled={isUploading}>
          <Icon name="send" size={14} />
          Send
        </button>
        <button className="btn btn-demo" onClick={runDemo} disabled={isUploading}>
          <Icon name="play" size={12} />
          Demo
        </button>
        <button
          className="btn btn-secondary"
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          title="Upload custom markdown or text document to corpus"
        >
          <Icon name="upload" size={14} />
          {isUploading ? 'Indexing…' : 'Upload Doc'}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".md,.txt,.markdown"
          style={{ display: 'none' }}
          onChange={handleFileUpload}
          disabled={isUploading}
        />
        <button className="btn btn-secondary" onClick={resetSession} disabled={isUploading} title="Reset sessions and custom uploads; keep the permanent test document">
          <Icon name="reset" size={14} />
          Reset
        </button>

        <button
          className="btn btn-secondary"
          onClick={async () => {
            showToast('Running evaluation test suite...', 'warn');
            try {
              const res = await fetch('/api/test-suite/run', { method: 'POST' });
              const data = await res.json();
              if (data.status === 'success') {
                console.log(data.output);
                showToast('Test suite completed! See console for details.', 'success');
              } else {
                console.error(data.output);
                showToast('Test suite failed! See console for details.', 'warn');
              }
            } catch (err) {
              console.error(err);
              showToast('Error running test suite.', 'warn');
            }
          }}
          disabled={isUploading}
          title="Run PRISM evaluation examples on isolated test corpus"
        >
          <Icon name="file" size={14} />
          Run Test Suite
        </button>
      </div>

      {toast && (
        <div className={`toast-notification ${toast.type}`}>
          <span className="toast-icon">
            <Icon name={toast.type === 'success' ? 'check' : toast.type === 'warn' ? 'warning' : 'file'} size={14} />
          </span>
          <span>{toast.message}</span>
        </div>
      )}
    </>
  );
}

