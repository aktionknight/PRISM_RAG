import React, { useState, useEffect, useRef } from 'react';
import './index.css';
import MetricsPanel from './components/MetricsPanel';

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
  const [status, setStatus] = useState(STATUS_CONNECTING);
  const [sessionId, setSessionId] = useState('—');
  const [chunks, setChunks] = useState([]);
  const [subQueries, setSubQueries] = useState([]);
  const [retrievals, setRetrievals] = useState([]);
  const [streamingTokens, setStreamingTokens] = useState([]);
  const [finalAnswer, setFinalAnswer] = useState(null);
  const [citations, setCitations] = useState([]);
  const [uncertainties, setUncertainties] = useState([]);
  
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
  const wsRef = useRef(null);
  
  const streamPaneRef = useRef(null);
  const answerPaneRef = useRef(null);

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

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

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
        setStreamingTokens(prev => [...prev, msg]);
        break;

      case 'answer_version': {
        setStreamingTokens([]);
        setFinalAnswer({
          version: msg.version || 1,
          turn_id: msg.turn_id || 1,
          answer: msg.answer || '',
        });
        setCitations(msg.citations || []);
        // Extract telemetry data from synthesis result
        const tel = msg.telemetry || {};
        setStats(s => ({
          ...s,
          answerVersion: msg.version || 1,
          turnId: msg.turn_id || 1,
          claimCount: (msg.claims || []).length,
          citationsCount: (msg.citations || []).length,
          totalTokens: (tel.total_tokens_prompt || 0) + (tel.total_tokens_completion || 0),
          totalTokensPrompt: tel.total_tokens_prompt || s.totalTokensPrompt,
          totalTokensCompletion: tel.total_tokens_completion || s.totalTokensCompletion,
          totalCost: tel.total_cost_usd || s.totalCost,
          synthesisLatency: tel.synthesis_latency_ms || 0,
          llmCallsThisTurn: tel.total_llm_calls || 0,
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

  const resetSession = () => {
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
  };

  const sendQuery = () => {
    const text = inputVal.trim();
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    
    setInputVal('');
    
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
      <header className="header">
        <div className="header-left">
          <div>
            <div className="logo">PRISM</div>
            <div className="logo-sub">Streaming Live RAG Engine</div>
          </div>
        </div>
        <div className="header-right">
          <div className={`status-dot ${status === STATUS_CONNECTED ? '' : 'disconnected'}`}></div>
          <span className="status-text">{status}</span>
          <span className="session-id">{sessionId}</span>
        </div>
      </header>

      <main className="main">
        {/* Left Pane: Live Stream */}
        <div className="pane">
          <div className="pane-header">
            <span className="pane-title">Live Stream</span>
            <span className="pane-badge" style={{background:'rgba(99,102,241,0.12)', color:'var(--accent-indigo)'}}>
              {chunks.length} chunks
            </span>
          </div>
          <div className="pane-body" ref={streamPaneRef}>
            {chunks.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">📡</div>
                <div className="empty-state-text">Waiting for transcript chunks…</div>
              </div>
            ) : (
              chunks.map((msg, i) => {
                const decision = msg.decision;
                let badgeClass = 'badge-wait';
                let badgeText = 'WAIT';
                if (decision === 'RETRIEVE') { badgeClass = 'badge-retrieve'; badgeText = '⚡ RETRIEVE'; }
                else if (decision === 'NO_RETRIEVAL') { badgeClass = 'badge-suppress'; badgeText = '🛑 SUPPRESS'; }

                const conf = msg.confidence || 0;
                const confPct = Math.round(conf * 100);
                const confColor = conf > 0.7 ? 'var(--accent-emerald)' : conf > 0.4 ? 'var(--accent-amber)' : 'var(--accent-rose)';

                return (
                  <div key={i} className="chunk-item">
                    <div className="chunk-time">{(msg.t_s || 0).toFixed(1)}s</div>
                    <div className="chunk-content">
                      <div className="chunk-text">{msg.prefix || ''}</div>
                      <span className={`chunk-badge ${badgeClass}`}>{badgeText}</span>
                      <span style={{fontSize:'10px', color:'var(--text-dim)', marginLeft:'6px'}}>{msg.reason || ''}</span>
                      <span className="confidence-bar">
                        <span className="confidence-fill" style={{width: `${confPct}%`, background: confColor}}></span>
                      </span>
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
            <span className="pane-title">Answer</span>
            <div style={{display:'flex', gap:'8px', alignItems:'center'}}>
              <span className="pane-badge" style={{background:'rgba(16,185,129,0.12)', color:'var(--accent-emerald)'}}>
                V{stats.answerVersion}
              </span>
            </div>
          </div>
          <div className="pane-body" ref={answerPaneRef}>
            {chunks.length === 0 && !finalAnswer && streamingTokens.length === 0 && subQueries.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">💬</div>
                <div className="empty-state-text">Ask a question to see the grounded answer</div>
              </div>
            ) : (
              <>
                {subQueries.length > 0 && (
                  <div className="sub-queries-box">
                    {subQueries.map((q, i) => (
                      <span key={i} className="sub-query-tag">{q}</span>
                    ))}
                  </div>
                )}
                
                {finalAnswer && (
                  <div className="version-info">
                    <span className="version-badge">V{finalAnswer.version}</span>
                    <span>Turn {finalAnswer.turn_id}</span>
                    <span>•</span>
                    <span>{citations.length} citations</span>
                  </div>
                )}

                {finalAnswer ? (
                  <div className="answer-section fade-in">
                    <div 
                      className="answer-sentence committed"
                      dangerouslySetInnerHTML={{
                        __html: escapeHtml(finalAnswer.answer).replace(/\[(Doc_\d+\s*§\w+)\]/g, '<span class="citation-chip">$1</span>')
                      }}
                    />
                  </div>
                ) : (
                  streamingTokens.map((t, i) => (
                    <div key={i} className={`answer-sentence ${t.kind || 'provisional'} fade-in`}>
                      {t.text || ''} 
                      {(t.citations || []).map((c, j) => (
                        <span key={j} className="citation-chip" title={c}>{c}</span>
                      ))}
                    </div>
                  ))
                )}

                {citations.length > 0 && finalAnswer && (
                  <div style={{display:'flex', flexWrap:'wrap', gap:'6px', marginTop:'12px'}}>
                    {citations.map((c, i) => (
                      <span key={i} className="citation-chip">{c}</span>
                    ))}
                  </div>
                )}

                {uncertainties.map((u, i) => (
                  <div key={i} className="uncertainty-box fade-in">
                    {u}
                  </div>
                ))}
              </>
            )}
          </div>
        </div>

        {/* Right Pane: Metrics & Telemetry */}
        <div className="pane">
          <div className="pane-header">
            <span className="pane-title">Metrics & Telemetry</span>
            <span className="pane-badge" style={{background:'rgba(6,182,212,0.12)', color:'var(--accent-cyan)'}}>
              {stats.telemetryEventCount} events
            </span>
          </div>
          <div className="pane-body" style={{padding: 0}}>
            <MetricsPanel telemetryData={telemetryData} sessionStats={stats} />
            {/* Retrieval Gantt - Kept in main UI for quick visibility */}
            <div style={{padding: '16px', borderBottom: '1px solid var(--border-glass)'}}>
              <div style={{fontSize:'11px', fontWeight:600, color:'var(--text-secondary)', marginBottom:'10px', textTransform:'uppercase', letterSpacing:'0.5px'}}>
                ⏱️ RETRIEVAL TIMELINE
              </div>
              <div>
                {retrievals.length === 0 ? (
                  <div style={{fontSize:'11px', color:'var(--text-dim)'}}>No retrievals yet</div>
                ) : (() => {
                  const maxTs = Math.max(...retrievals.map(e => e.timestamp_s || 0), 1);
                  return retrievals.map((ev, idx) => {
                    const left = ((ev.timestamp_s || 0) / (maxTs + 0.5)) * 100;
                    const width = Math.max(15, 100 - left);
                    const isSpec = ev.trigger === 'provisional';
                    return (
                      <div key={idx} className="gantt-bar">
                        <span className="gantt-label" title={ev.query || ''}>{ev.facet || ev.query || `Q${idx + 1}`}</span>
                        <div className="gantt-track">
                          <div className={`gantt-fill ${isSpec ? 'speculative' : 'confirmed'}`} style={{left:`${left}%`, width:`${width}%`}}></div>
                        </div>
                        <span style={{fontSize:'10px', color:'var(--text-dim)'}}>{(ev.timestamp_s || 0).toFixed(1)}s</span>
                      </div>
                    );
                  });
                })()}
              </div>
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
        />
        <button id="sendBtn" className="btn btn-primary" onClick={sendQuery}>
          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
          Send
        </button>
        <button className="btn btn-demo" onClick={runDemo}>▶ Demo</button>
        <button className="btn btn-secondary" onClick={resetSession}>↻ Reset</button>
      </div>
    </>
  );
}
