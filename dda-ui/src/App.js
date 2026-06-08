import React, { useState, useEffect, useCallback, useRef } from "react";

const API = "https://dda-query-service-a2bgowuvzq-uc.a.run.app";
const UPLOAD_API = process.env.UPLOAD_URL || "https://dda-upload-service-a2bgowuvzq-uc.a.run.app"; // Update with actual URL

const DEMOS = [
  "Which customers received the largest discounts and why?",
  "What was the approval process for discounts above 15%?",
  "What pricing strategies drove margin decline 2016-2018?",
  "Which products had the most pricing variability?",
  "What competitive pressures affected our pricing in 2020?",
  "Who approved the discount for Acme Corp in 2021?",
  "Show me all contracts from NovaTech Inc.",
  "Are there any pricing inconsistencies between different price lists for the same product?",
  "Summarize the key decisions made by VP Sales in Q1 2017.",
  "Find all documents related to Quantum Dynamics.",
];

const css = `
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=Inter:wght@300;400;500;600;700&display=swap');
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  :root{
    --void:#0c0f12;--deep:#161a1f;--surf:#20262c;--raise:#2a313a;--hover:#343d47;
    --acc:#4a90e2;--acc-hi:#60a1f0;--acc-lo:#3a72bb;--acc-glow:rgba(74,144,226,0.15);
    --t1:#e0e6ed;--t2:#aab2bc;--t3:#6a737f;
    --bdr:rgba(255,255,255,0.07);--bdr-a:rgba(74,144,226,0.3);
    --green:#4CAF50;--red:#F44336;--font-m:'IBM Plex Mono',monospace;--font-p:'Inter',sans-serif;
  }
  body{background:var(--void);color:var(--t1);font-family:var(--font-p);font-size:13px;line-height:1.6;min-height:100vh}
  .shell{display:grid;grid-template-columns:210px 1fr;grid-template-rows:54px 1fr;min-height:100vh}
  .hdr{grid-column:1/-1;display:flex;align-items:center;gap:14px;padding:0 22px;background:var(--deep);border-bottom:1px solid var(--bdr);position:sticky;top:0;z-index:100}
  .logo{font-size:17px;font-weight:700;color:var(--acc-hi);letter-spacing:-0.5px;white-space:nowrap}
  .logo span{color:var(--t3);font-weight:300}
  .htag{font-size:9px;color:var(--t3);border:1px solid var(--bdr);padding:2px 8px;border-radius:2px;letter-spacing:1px}
  .hstat{margin-left:auto;font-size:10px;color:var(--t3);display:flex;align-items:center;gap:8px;white-space:nowrap}
  .dot{width:6px;height:6px;border-radius:50%;background:var(--green);box-shadow:0 0 5px var(--green);animation:pulse 2.2s infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.35}}
  .side{background:var(--deep);border-right:1px solid var(--bdr);padding:20px 0;overflow-y:auto}
  .nlbl{font-size:8px;letter-spacing:2px;color:var(--t3);padding:0 16px;margin:16px 0 7px}
  .nlbl:first-child{margin-top:0}
  .nitem{display:flex;align-items:center;gap:10px;padding:8px 16px;cursor:pointer;color:var(--t2);font-size:11px;border-left:2px solid transparent;transition:all 0.13s;user-select:none}
  .nitem:hover{background:var(--hover);color:var(--t1)}
  .nitem.act{color:var(--acc-hi);border-left-color:var(--acc);background:var(--surf)}
  .nicon{font-size:13px;width:17px;text-align:center;flex-shrink:0}
  .mstat-wrap{padding:0 16px;margin-top:22px;border-top:1px solid var(--bdr);padding-top:16px}
  .mrow{display:flex;justify-content:space-between;font-size:10px;color:var(--t3);padding:2px 0}
  .mv{color:var(--acc)}
  .main{overflow-y:auto;background:var(--void)}
  .page{padding:30px 34px;max-width:1080px}
  .ptitle{font-size:24px;font-weight:700;color:var(--t1);margin-bottom:3px;letter-spacing:-0.5px}
  .psub{font-size:9px;color:var(--t3);letter-spacing:1.5px;margin-bottom:26px}
  .sgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:26px}
  .scard{background:var(--surf);border:1px solid var(--bdr);border-top:2px solid var(--acc-lo);border-radius:5px;padding:18px}
  .sval{font-size:30px;font-weight:700;color:var(--acc-hi);line-height:1;margin-bottom:5px}
  .slbl{font-size:9px;color:var(--t3);letter-spacing:1px}
  .sec{font-size:9px;letter-spacing:2px;color:var(--t3);margin-bottom:12px;display:flex;align-items:center;gap:10px}
  .sec::after{content:'';flex:1;height:1px;background:var(--bdr)}
  .strack{height:5px;background:var(--raise);border-radius:3px;overflow:hidden;display:flex;margin-bottom:10px;gap:1px}
  .s1{background:var(--t3)}.s2{background:var(--acc-lo)}.s3{background:var(--acc)}
  .leg{display:flex;gap:22px;margin-bottom:22px}
  .li{display:flex;align-items:center;gap:7px;font-size:10px;color:var(--t2)}
  .ld{width:7px;height:7px;border-radius:1px;flex-shrink:0}
  .srow{display:flex;align-items:center;gap:12px;margin-bottom:9px}
  .sbar-wrap{flex:1;background:var(--raise);height:4px;border-radius:2px;overflow:hidden}
  .sbar-fill{height:100%;background:linear-gradient(90deg,var(--acc-lo),var(--acc));border-radius:2px}
  .qbox{background:var(--surf);border:1px solid var(--bdr);border-radius:7px;padding:22px;margin-bottom:22px}
  textarea{width:100%;background:var(--deep);border:1px solid var(--bdr);border-radius:4px;color:var(--t1);font-family:var(--font-m);font-size:12px;padding:13px 15px;resize:vertical;min-height:72px;outline:none;transition:border-color 0.13s;line-height:1.6}
  textarea:focus{border-color:var(--bdr-a)}
  textarea::placeholder{color:var(--t3)}
  .qact{display:flex;gap:10px;margin-top:11px;align-items:center}
  .btnp{background:var(--acc);color:var(--void);border:none;padding:9px 22px;border-radius:4px;font-family:var(--font-p);font-size:11px;font-weight:600;cursor:pointer;letter-spacing:0.5px;transition:background 0.13s;white-space:nowrap}
  .btnp:hover:not(:disabled){background:var(--acc-hi)}
  .btnp:disabled{opacity:0.45;cursor:not-allowed}
  .btns{background:transparent;color:var(--t2);border:1px solid var(--bdr);padding:8px 15px;border-radius:4px;font-family:var(--font-p);font-size:11px;cursor:pointer;transition:all 0.13s}
  .btns:hover{border-color:var(--bdr-a);color:var(--t1)}
  .qmeta{margin-left:auto;font-size:9px;color:var(--t3)}
  .demo-lbl{font-size:9px;color:var(--t3);letter-spacing:1px;margin:16px 0 8px}
  .chips{display:flex;gap:7px;flex-wrap:wrap}
  .chip{background:var(--raise);border:1px solid var(--bdr);border-radius:100px;padding:4px 13px;font-size:10px;color:var(--t2);cursor:pointer;white-space:nowrap;transition:all 0.13s;user-select:none}
  .chip:hover{border-color:var(--bdr-a);color:var(--acc-hi)}
  .lbar{height:1px;background:linear-gradient(90deg,transparent,var(--acc),transparent);animation:lb 1.3s infinite;margin-bottom:18px}
  @keyframes lb{0%{transform:translateX(-100%)}100%{transform:translateX(500%)}}
  .lwrap{overflow:hidden}
  .acard{background:var(--surf);border:1px solid var(--bdr);border-radius:7px;overflow:hidden;margin-bottom:22px;animation:fadeup 0.28s ease}
  @keyframes fadeup{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:translateY(0)}}
  .ahdr{background:var(--raise);padding:12px 20px;display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--bdr);flex-wrap:wrap;row-gap:6px}
  .ahlbl{font-size:9px;letter-spacing:1.5px;color:var(--acc)}
  .lat{margin-left:auto;font-size:9px;color:var(--t3)}
  .cpill{padding:2px 10px;border-radius:100px;font-size:9px;font-weight:600;letter-spacing:0.5px;flex-shrink:0}
  .chi{background:rgba(76,175,80,0.15);color:var(--green);border:1px solid rgba(76,175,80,0.25)}
  .cmd{background:rgba(74,144,226,0.15);color:var(--acc);border:1px solid rgba(74,144,226,0.25)}
  .clo{background:rgba(244,67,54,0.15);color:var(--red);border:1px solid rgba(244,67,54,0.25)}
  .hitl{background:rgba(244,67,54,0.07);border-top:1px solid rgba(244,67,54,0.18);padding:9px 20px;font-size:10px;color:var(--red)}
  .abody{padding:20px}
  .atxt{font-size:12px;line-height:1.9;color:var(--t1);white-space:pre-wrap;margin-bottom:18px}
  .ctog{font-size:10px;color:var(--acc);cursor:pointer;margin-bottom:11px;display:flex;align-items:center;gap:6px;user-select:none}
  .ctog:hover{color:var(--acc-hi)}
  .cit{background:var(--raise);border-left:2px solid var(--acc-lo);padding:9px 13px;margin-bottom:7px;border-radius:0 4px 4px 0}
  .cfn{color:var(--acc-hi);font-size:10px;font-weight:600;margin-bottom:4px}
  .cex{color:var(--t2);font-size:10px;line-height:1.55}
  .cco{color:var(--t3);font-size:9px;margin-top:3px}
  .fbar{display:flex;gap:8px;margin-bottom:18px;flex-wrap:wrap}
  select{background:var(--surf);border:1px solid var(--bdr);color:var(--t2);font-family:var(--font-m);font-size:10px;padding:6px 11px;border-radius:4px;outline:none;cursor:pointer}
  select:focus{border-color:var(--bdr-a)}
  .agrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:11px}
  .acard2{background:var(--surf);border:1px solid var(--bdr);border-radius:5px;padding:15px;transition:border-color 0.13s}
  .acard2:hover{border-color:var(--bdr-a)}
  .afn{color:var(--acc-hi);font-size:11px;font-weight:600;margin-bottom:8px;word-break:break-all;line-height:1.4}
  .ameta{display:flex;gap:6px;flex-wrap:wrap}
  .atag{background:var(--deep);border:1px solid var(--bdr);border-radius:2px;padding:1px 7px;font-size:9px;color:var(--t3);letter-spacing:0.5px}
  .atag.enr{border-color:var(--green);color:var(--green)}
  .atag.cor{border-color:var(--acc-lo);color:var(--acc)}
  .gwrap{background:var(--surf);border:1px solid var(--bdr);border-radius:7px;overflow:hidden;position:relative}
  .gwrap svg{display:block;width:100%}
  .gleg{margin-top:11px;font-size:9px;color:var(--t3);display:flex;gap:22px;flex-wrap:wrap}
  .gleg-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;display:inline-block;margin-right:5px}
  .gtooltip{position:absolute;background:var(--deep);border:1px solid var(--bdr-a);border-radius:4px;padding:8px 12px;font-size:10px;color:var(--t1);pointer-events:none;max-width:260px;line-height:1.5;z-index:10;white-space:pre-wrap;word-break:break-word}
  .rel-list{margin-top:18px}
  .rel-row{display:flex;align-items:flex-start;gap:10px;padding:9px 0;border-bottom:1px solid var(--bdr);font-size:10px}
  .rel-type{background:var(--raise);border:1px solid var(--bdr);border-radius:2px;padding:1px 7px;font-size:9px;color:var(--acc);white-space:nowrap;flex-shrink:0}
  .rel-docs{flex:1;color:var(--t2);line-height:1.6}
  .rel-conf{color:var(--t3);font-size:9px;flex-shrink:0;margin-top:2px}
  .dec-list{margin-top:18px}
  .dec-row{background:var(--raise);border-left:2px solid var(--acc-lo);padding:10px 14px;margin-bottom:8px;border-radius:0 4px 4px 0}
  .dec-head{display:flex;gap:10px;align-items:center;margin-bottom:4px;flex-wrap:wrap}
  .dec-actor{color:var(--acc-hi);font-size:10px;font-weight:600}
  .dec-date{color:var(--t3);font-size:9px}
  .dec-seg{background:var(--deep);padding:1px 7px;border-radius:2px;font-size:9px;color:var(--t2)}
  .dec-rat{color:var(--t2);font-size:10px;line-height:1.55}
  .dec-imp{color:var(--acc);font-size:10px;margin-top:3px}
  .dz{border:1.5px dashed var(--bdr);border-radius:7px;padding:54px 40px;text-align:center;background:var(--surf);transition:all 0.18s;margin-bottom:22px;cursor:pointer}
  .dz.over{border-color:var(--acc);background:var(--hover)}
  .err{background:rgba(244,67,54,0.07);border:1px solid rgba(244,67,54,0.2);border-radius:5px;padding:10px 15px;font-size:11px;color:var(--red);margin-bottom:18px}
  .ok{background:rgba(76,175,80,0.07);border:1px solid rgba(76,175,80,0.2);border-radius:5px;padding:10px 15px;font-size:11px;color:var(--green);margin-bottom:18px}
  .hrow{display:flex;align-items:center;gap:11px;padding:8px 0;border-bottom:1px solid var(--bdr);cursor:pointer}
  .hrow:hover{background:var(--hover)}
  .hq{flex:1;font-size:11px;color:var(--t2)}
  .hrow:hover .hq{color:var(--t1)}
  .empty{text-align:center;padding:56px 20px;color:var(--t3)}
  .frow{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--bdr)}
  .fq{flex:1;font-size:11px;color:var(--t2)}
  .upload-grid{display:grid;grid-template-columns:1fr 1fr;gap:11px;margin-bottom:18px}
  .ucard{background:var(--surf);border:1px solid var(--bdr);border-radius:5px;padding:14px}
  .ufn{color:var(--acc-hi);font-size:11px;font-weight:600;margin-bottom:6px;word-break:break-all}
  .ustatus{display:flex;align-items:center;gap:8px;font-size:10px;margin-top:8px}
  .uprog{flex:1;background:var(--raise);height:3px;border-radius:2px;overflow:hidden}
  .uprog-fill{height:100%;border-radius:2px;transition:width 0.4s ease}
  .streaming-cursor{display:inline-block;width:8px;height:13px;background:var(--acc);animation:blink 0.85s step-end infinite;vertical-align:text-bottom;margin-left:2px}
  @keyframes blink{0%,100%{opacity:1}50%{opacity:0}}
`;

function confPill(s) {
  if (s === undefined || s === null) return null;
  const [cls, lbl] = s >= 0.85 ? ["chi","HIGH"] : s >= 0.75 ? ["cmd","MED"] : ["clo","LOW"];
  return React.createElement("span", {className: "cpill " + cls},
    "CONF " + lbl + " " + Math.round(s * 100) + "%");
}

// ── Dashboard ──────────────────────────────────────────────────────────────
function Dashboard({ status, loading }) {
  if (loading) return React.createElement("div", {className:"page"},
    React.createElement("div", {className:"ptitle"}, "Dark Data Archaeologist"),
    React.createElement("div", {className:"psub"}, "PIPELINE INTELLIGENCE DASHBOARD · LIVE"),
    React.createElement("div", {className:"lwrap"}, React.createElement("div", {className:"lbar"})));

  if (!status) return React.createElement("div", {className:"page"},
    React.createElement("div", {className:"ptitle"}, "Dark Data Archaeologist"),
    React.createElement("div", {className:"psub"}, "PIPELINE INTELLIGENCE DASHBOARD · LIVE"),
    React.createElement("div", {className:"empty"}, "Cannot reach query service."));

  const st = status.pipeline_stages || {}, total = status.total_artifacts || 0;
  const ing = st.INGESTED || 0, cor = st.CORRELATED || 0, enr = st.ENRICHED || 0;
  const pct = v => total ? (v / total * 100).toFixed(1) + "%" : "0%";

  return React.createElement("div", {className:"page"},
    React.createElement("div", {className:"ptitle"}, "Dark Data Archaeologist"),
    React.createElement("div", {className:"psub"}, "PIPELINE INTELLIGENCE DASHBOARD · LIVE"),
    React.createElement("div", {className:"sgrid"},
      React.createElement("div", {className:"scard"}, React.createElement("div", {className:"sval"}, total), React.createElement("div", {className:"slbl"}, "TOTAL ARTIFACTS")),
      React.createElement("div", {className:"scard"}, React.createElement("div", {className:"sval"}, status.relationships >= 0 ? status.relationships : "—"), React.createElement("div", {className:"slbl"}, "RELATIONSHIPS (BQ)")),
      React.createElement("div", {className:"scard"}, React.createElement("div", {className:"sval"}, status.decisions >= 0 ? status.decisions : "—"), React.createElement("div", {className:"slbl"}, "DECISIONS EXTRACTED")),
      React.createElement("div", {className:"scard"}, React.createElement("div", {className:"sval"}, total ? Math.round(enr / total * 100) + "%" : "0%"), React.createElement("div", {className:"slbl"}, "QUERY-READY"))
      ),
      React.createElement("div", {className:"sec"}, "PIPELINE STAGE DISTRIBUTION"),
      React.createElement("div", {className:"strack"},
      React.createElement("div", {className:"s1", style:{width:pct(ing)}}),
      React.createElement("div", {className:"s2", style:{width:pct(cor)}}),
      React.createElement("div", {className:"s3", style:{width:pct(enr)}})
      ),
      React.createElement("div", {className:"leg"},
      React.createElement("div", {className:"li"}, React.createElement("div", {className:"ld", style:{background:"var(--t3)"}}), "INGESTED (" + ing + ")"),
      React.createElement("div", {className:"li"}, React.createElement("div", {className:"ld", style:{background:"var(--acc-lo)"}}), "CORRELATED (" + cor + ")"),
      React.createElement("div", {className:"li"}, React.createElement("div", {className:"ld", style:{background:"var(--acc)"}}), "ENRICHED (" + enr + ")")
      ),
      React.createElement("div", {className:"sec"}, "STAGE BREAKDOWN"),
      ...Object.entries(st).map(([k, v]) =>
      React.createElement("div", {key:k, className:"srow"},
        React.createElement("div", {style:{width:108,fontSize:10,color:"var(--t3)"}}, k),
        React.createElement("div", {className:"sbar-wrap"}, React.createElement("div", {className:"sbar-fill", style:{width:pct(v)}})),
        React.createElement("div", {style:{width:22,textAlign:"right",fontSize:11,color:"var(--acc-hi)"}}, v)
      )
      )
      );
      }
// ── Answer View ────────────────────────────────────────────────────────────
function AnswerView({ result, streaming, streamText }) {
  const [showCit, setShowCit] = useState(true);

  if (streaming) {
    return (
      <div className="acard">
        <div className="ahdr">
          <span className="ahlbl">§ SYNTHESIZING…</span>
          <span className="lat">Gemini generating response</span>
        </div>
        <div className="abody">
          <div className="atxt">
            {streamText}
            <span className="streaming-cursor"/>
          </div>
        </div>
      </div>
    );
  }

  if (!result) return null;
  const { answer, citations = [], overall_confidence, requires_human_review, query_latency_ms, trace_id } = result;
  const cits = citations.filter(c => c.filename || c.artifact_id);
  return (
    <div className="acard">
      <div className="ahdr">
        <span className="ahlbl">§ SYNTHESIS RESULT</span>
        {confPill(overall_confidence)}
        <span className="lat">{query_latency_ms}ms · trace:{(trace_id||"").slice(0,8)}</span>
      </div>
      {requires_human_review && <div className="hitl">⚠ LOW CONFIDENCE — HUMAN REVIEW RECOMMENDED</div>}
      <div className="abody">
        <div className="atxt">{answer}</div>
        {cits.length > 0 && <>
          <div className="ctog" onClick={() => setShowCit(v => !v)}>
            § {cits.length} SOURCE{cits.length !== 1 ? "S" : ""} {showCit ? "▴" : "▾"}
          </div>
          {showCit && cits.map((c, i) => (
            <div key={i} className="cit">
              <div className="cfn">{c.filename || c.artifact_id}</div>
              {c.excerpt && <div className="cex">{c.excerpt.slice(0,220)}{c.excerpt.length>220?"…":""}</div>}
              <div className="cco">confidence: {c.confidence != null ? c.confidence.toFixed(2) : "—"}</div>
            </div>
          ))}
        </>}
      </div>
    </div>
  );
}

// ── Query Page ────────────────────────────────────────────────────────────
function QueryPage() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);

  const run = useCallback(async (q) => {
    const text = (q || query).trim();
    if (!text) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setStreaming(false);
    setStreamText("");

    try {
      const r = await fetch(API + "/v1/query", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify({user_id:"ui-user", session_id:Date.now()+"", query:text})
      });
      if (!r.ok) throw new Error("HTTP " + r.status);

      // Simulate streaming reveal while waiting for JSON
      setLoading(false);
      setStreaming(true);

      const d = await r.json();

      // Animate answer text char by char for perceived speed
      setStreaming(false);
      setResult(d);
      setHistory(h => [{q:text, conf:d.overall_confidence}, ...h].slice(0,8));
    } catch(e) {
      setLoading(false);
      setStreaming(false);
      setError("API error: " + e.message);
    }
  }, [query]);

  return (
    <div className="page">
      <div className="ptitle">Intelligence Query</div>
      <div className="psub">NATURAL LANGUAGE ARCHIVE RETRIEVAL · GEMINI SYNTHESIS</div>
      <div className="qbox">
        <textarea
          placeholder="Ask anything about pricing history, discount patterns, or approval chains…"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => { if (e.key==="Enter" && (e.metaKey||e.ctrlKey)) run(); }}
          rows={3}
        />
        <div className="qact">
          <button className="btnp" onClick={() => run()} disabled={loading || streaming || !query.trim()}>
            {loading ? "CONNECTING…" : streaming ? "SYNTHESIZING…" : "QUERY ARCHIVE"}
          </button>
          {(query || result) && (
            <button className="btns" onClick={() => {setQuery("");setResult(null);setError(null);setStreaming(false);}}>
              CLEAR
            </button>
          )}
          <span className="qmeta">⌘↵ to submit</span>
        </div>
        <div className="demo-lbl">DEMO QUERIES</div>
        <div className="chips">
          {DEMOS.map((d,i) => (
            <div key={i} className="chip" onClick={() => {setQuery(d); run(d);}}>
              {d.length > 50 ? d.slice(0,50)+"…" : d}
            </div>
          ))}
        </div>
      </div>

      {loading && <div className="lwrap"><div className="lbar"/></div>}
      {error && <div className="err">⚠ {error}</div>}

      <AnswerView result={result} streaming={streaming} streamText={streamText} />

      {history.length > 0 && <>
        <div className="sec" style={{marginTop:8}}>QUERY HISTORY</div>
        {history.map((h,i) => (
          <div key={i} className="hrow" onClick={() => {setQuery(h.q); run(h.q);}}>
            <span style={{color:"var(--t3)",fontSize:11}}>⌖</span>
            <span className="hq">{h.q}</span>
            {confPill(h.conf)}
          </div>
        ))}
      </>}
    </div>
  );
}

// ── Artifact Explorer ───────────────────────────────────────────────────────
function ArtifactExplorer({ page }) { // Accept page prop
  const [arts, setArts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [typeF, setTypeF] = useState("all");
  const [stageF, setStageF] = useState("all");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(API + "/v1/artifacts");
      const d = await r.json();
      setArts(d.artifacts || []);
    } catch (e) {
      console.error("Failed to fetch artifacts:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (page === "artifacts") { // Only fetch if this page is active
      fetchData();
      const interval = setInterval(fetchData, 30000); // Refresh every 30 seconds
      return () => clearInterval(interval); // Cleanup on unmount or page change
    }
  }, [page, fetchData]);

  if (loading) return (
    <div className="page">
      <div className="ptitle">Artifact Registry</div>
      <div className="lwrap"><div className="lbar"/></div>
    </div>
  );

  const types  = ["all", ...new Set(arts.map(a => a.document_type).filter(Boolean))];
  const stages = ["all", ...new Set(arts.map(a => a.pipeline_stage).filter(Boolean))];
  const filtered = arts.filter(a =>
    (typeF==="all" || a.document_type===typeF) &&
    (stageF==="all" || a.pipeline_stage===stageF)
  );

  return (
    <div className="page">
      <div className="ptitle">Artifact Registry</div>
      <div className="psub">{filtered.length} OF {arts.length} DOCUMENTS</div>
      <div className="fbar">
        <select value={typeF} onChange={e => setTypeF(e.target.value)}>
          {types.map(t => <option key={t} value={t}>{t==="all"?"ALL TYPES":t.toUpperCase()}</option>)}
        </select>
        <select value={stageF} onChange={e => setStageF(e.target.value)}>
          {stages.map(s => <option key={s} value={s}>{s==="all"?"ALL STAGES":s}</option>)}
        </select>
      </div>
      {filtered.length === 0
        ? <div className="empty"><div style={{fontSize:28,marginBottom:10}}>⊞</div><div>No artifacts match filters</div></div>
        : <div className="agrid">
            {filtered.map(a => (
              <div key={a.artifact_id} className="acard2">
                <div className="afn">{a.filename}</div>
                <div className="ameta">
                  <span className="atag">{a.document_type}</span>
                  <span className={"atag "+(a.pipeline_stage==="ENRICHED"?"enr":a.pipeline_stage==="CORRELATED"?"cor":"")}>
                    {a.pipeline_stage}
                  </span>
                  {a.word_count && <span className="atag">{a.word_count}w</span>}
                  {a.extraction_confidence!=null && <span className="atag">{Math.round(a.extraction_confidence*100)}% conf</span>}
                </div>
                {a.pipeline_stage && a.pipeline_stage.includes("FAILED") && (
                  <div style={{fontSize:9,color:"#e07070",marginTop:8,lineHeight:1.4}}>
                    {a.pipeline_stage === "INGEST_FAILED" && `Ingest Error: ${a.ingest_error || 'Unknown'}`}
                    {a.pipeline_stage === "CORRELATE_FAILED" && `Correlate Error: ${a.correlate_error || 'Unknown'}`}
                    {a.pipeline_stage === "CORRELATED_PUB_FAIL" && `Correlate Pub/Sub Error: ${a.enrich_trigger_error || a.correlated_pub_fail || 'Unknown'}`}
                    {a.pipeline_stage === "ENRICH_FAILED" && `Enrich Error: ${a.enrich_error || 'Unknown'}`}
                  </div>
                )}
              </div>
            ))}
          </div>
      }
    </div>
  );
}

// ── Relationship Graph — REAL DATA from /v1/relationships ──────────────────
function RelGraph({ page }) { // Accept page prop
  const [rels, setRels]   = useState([]);
  const [decs, setDecs]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [tooltip, setTooltip] = useState(null);
  const [tooltipPos, setTooltipPos] = useState({x:0,y:0});
  const [selected, setSelected] = useState(null);
  const svgRef = useRef(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(API + "/v1/relationships");
      const d = await r.json();
      setRels(d.relationships || []);
      setDecs(d.decisions || []);
    } catch (e) {
      console.error("Failed to fetch relationships:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (page === "graph") { // Only fetch if this page is active
      fetchData();
      const interval = setInterval(fetchData, 30000); // Refresh every 30 seconds
      return () => clearInterval(interval); // Cleanup on unmount or page change
    }
  }, [page, fetchData]);

  // Build node list from relationships
  const buildGraph = () => {
    const W = 680, H = 420;
    const nodeMap = {};
    rels.forEach(r => {
      if (r.source_doc) nodeMap[r.source_doc] = true;
      if (r.target_doc) nodeMap[r.target_doc] = true;
    });
    const names = Object.keys(nodeMap);
    if (names.length === 0) return { nodes: [], edges: [] };

    // Distribute nodes in an ellipse with slight jitter for readability
    const nodes = names.map((name, i) => {
      const angle = (i / names.length) * Math.PI * 2 - Math.PI / 2;
      const rx = Math.min(240, 30 * names.length);
      const ry = Math.min(160, 20 * names.length);
      const jx = (Math.random() - 0.5) * 30;
      const jy = (Math.random() - 0.5) * 20;
      const color = name.includes("contract") ? "#c98f18"
                  : name.includes("email")    ? "#3d7a56"
                  : name.includes("price")    ? "#5a7898"
                  : "#7a5898";
      return {
        id: name,
        x: W / 2 + Math.cos(angle) * rx + jx,
        y: H / 2 + Math.sin(angle) * ry + jy,
        color,
        short: name.replace(/\.(pdf|docx|csv)$/i,"").replace(/_/g," ").slice(0,16),
      };
    });

    const edges = rels.map(r => {
      const s = nodes.find(n => n.id === r.source_doc);
      const t = nodes.find(n => n.id === r.target_doc);
      return s && t ? { ...r, x1:s.x, y1:s.y, x2:t.x, y2:t.y } : null;
    }).filter(Boolean);

    return { nodes, edges };
  };

  const { nodes, edges } = buildGraph();

  const relTypeColor = t => {
    const m = {
      discount_approved:"var(--acc)",
      price_referenced:"#5a7898",
      company_shared:"var(--green)",
      decision_chain:"#b05858",
      same_customer:"#7a5898",
      anomaly_detected:"var(--red)",
    };
    return m[t] || "var(--t3)";
  };

  return (
    <div className="page">
      <div className="ptitle">Relationship Graph</div>
      <div className="psub">LIVE KNOWLEDGE GRAPH · BIGQUERY RELATIONSHIP EDGES</div>

      {loading && <div className="lwrap"><div className="lbar"/></div>}

      {!loading && nodes.length === 0 && (
        <div className="empty">
          <div style={{fontSize:28,marginBottom:10}}>⋈</div>
          <div>No relationships found in BigQuery.</div>
          <div style={{fontSize:10,marginTop:6,color:"var(--t3)"}}>Run CORRELATE agent first.</div>
        </div>
      )}

      {!loading && nodes.length > 0 && (
        <>
          <div className="gwrap" style={{marginBottom:18}}>
            <svg ref={svgRef} width="100%" height="420" viewBox="0 0 680 420"
              onMouseLeave={() => setTooltip(null)}>
              <defs>
                <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3"
                  orient="auto" markerUnits="strokeWidth">
                  <path d="M0,0 L0,6 L8,3 z" fill="rgba(74,144,226,0.4)"/>
                </marker>
              </defs>

              {/* Edges */}
              {edges.map((e, i) => {
                const isSelected = selected === e.source_doc || selected === e.target_doc;
                return (
                  <line key={i}
                    x1={e.x1} y1={e.y1} x2={e.x2} y2={e.y2}
                    stroke={isSelected ? relTypeColor(e.relationship_type) : "rgba(74,144,226,0.15)"}
                    strokeWidth={isSelected ? 1.5 : 1}
                    markerEnd="url(#arrow)"
                    strokeDasharray={isSelected ? "none" : "3,3"}
                    onMouseEnter={ev => {
                      const rect = svgRef.current.getBoundingClientRect();
                      setTooltipPos({
                        x: (e.x1 + e.x2) / 2 / 680 * rect.width,
                        y: (e.y1 + e.y2) / 2 / 420 * rect.height
                      });
                      setTooltip(`${e.relationship_type}\n${e.source_doc} → ${e.target_doc}\n\n${e.narrative || ""}\n\nconf: ${e.confidence}`);
                    }}
                    onMouseLeave={() => setTooltip(null)}
                    style={{cursor:"pointer"}}
                  />
                );
              })}

              {/* Nodes */}
              {nodes.map((n, i) => {
                const isSelected = selected === n.id;
                return (
                  <g key={i} style={{cursor:"pointer"}}
                    onClick={() => setSelected(s => s === n.id ? null : n.id)}
                    onMouseEnter={ev => {
                      const rect = svgRef.current.getBoundingClientRect();
                      setTooltipPos({ x: n.x / 680 * rect.width, y: n.y / 420 * rect.height - 20 });
                      const edgeCount = edges.filter(e => e.source_doc===n.id||e.target_doc===n.id).length;
                      setTooltip(`${n.id}\n\n${edgeCount} relationship${edgeCount!==1?"s":""}`);
                    }}
                    onMouseLeave={() => setTooltip(null)}>
                    <circle cx={n.x} cy={n.y} r={isSelected ? 16 : 10}
                      fill={n.color} fillOpacity={isSelected ? 0.3 : 0.12}
                      stroke={n.color} strokeWidth={isSelected ? 1.5 : 1}
                      style={{transition:"all 0.2s"}}/>
                    <circle cx={n.x} cy={n.y} r={isSelected ? 5 : 3} fill={n.color}/>
                    <text x={n.x} y={n.y + (isSelected?26:20)} textAnchor="middle"
                      fill={isSelected?"var(--acc-hi)":"var(--t3)"}
                      fontSize="8" fontFamily="IBM Plex Mono,monospace">
                      {n.short}
                    </text>
                  </g>
                );
              })}
            </svg>

            {tooltip && (
              <div className="gtooltip" style={{
                left: tooltipPos.x + 12,
                top: tooltipPos.y - 10,
                transform: tooltipPos.x > 500 ? "translateX(-100%)" : "none"
              }}>
                {tooltip}
              </div>
            )}
          </div>

          <div className="gleg">
            <span><span className="gleg-dot" style={{background:"var(--acc)"}}/>Contracts</span>
            <span><span className="gleg-dot" style={{background:"var(--green)"}}/>Email Threads</span>
            <span><span className="gleg-dot" style={{background:"#5a7898"}}/>Price Lists</span>
            <span style={{marginLeft:"auto",color:"var(--t3)"}}>Click node to highlight · hover edge for details</span>
          </div>

          {/* Relationship Table */}
          <div className="sec" style={{marginTop:26}}>RELATIONSHIP EDGES ({rels.length})</div>
          <div className="rel-list">
            {rels.map((r, i) => (
              <div key={i} className="rel-row">
                <span className="rel-type" style={{color:relTypeColor(r.relationship_type)}}>{r.relationship_type}</span>
                <span className="rel-docs">
                  <span style={{color:"var(--acc-hi)"}}>{r.source_doc}</span>
                  {" → "}
                  <span style={{color:"var(--t1)"}}>{r.target_doc}</span>
                  {r.narrative && <><br/><span style={{color:"var(--t3)"}}>{r.narrative}</span></>}
                </span>
                <span className="rel-conf">{r.confidence != null ? (r.confidence * 100).toFixed(0) + "%" : "—"}</span>
              </div>
            ))}
          </div>

          {/* Decisions Table */}
          {decs.length > 0 && <>
            <div className="sec" style={{marginTop:26}}>PRICING DECISIONS ({decs.length})</div>
            <div className="dec-list">
              {decs.map((d, i) => (
                <div key={i} className="dec-row">
                  <div className="dec-head">
                    {d.actor && <span className="dec-actor">{d.actor}</span>}
                    {d.date && <span className="dec-date">{d.date}</span>}
                    {d.affected_segment && <span className="dec-seg">{d.affected_segment}</span>}
                  </div>
                  {d.rationale && <div className="dec-rat">{d.rationale}</div>}
                  {d.impact_estimate && <div className="dec-imp">Impact: {d.impact_estimate}</div>}
                  {d.source_doc && <div style={{fontSize:9,color:"var(--t3)",marginTop:3}}>Source: {d.source_doc}</div>}
                </div>
              ))}
            </div>
          </>}
        </>
      )}
    </div>
  );
}

// ── Upload Page — WIRED to /v1/upload ─────────────────────────────────────
const ALLOWED_TYPES = ["application/pdf","application/vnd.openxmlformats-officedocument.wordprocessingml.document","text/csv"];
const ALLOWED_EXT   = [".pdf",".docx",".csv"];

function UploadPage() {
  const [dragging, setDragging]   = useState(false);
  const [files, setFiles]         = useState([]);   // {file, status, progress, error, artifact_id, pipeline_stage}
  const [submitting, setSubmitting] = useState(false);
  const [globalErr, setGlobalErr]  = useState(null);
  const [globalOk, setGlobalOk]    = useState(null);
  const inputRef = useRef(null);
  const pollingIntervals = useRef({}); // To store and clear polling intervals

  const PIPELINE_STAGE_PROGRESS = {
    UPLOADED: 25,
    INGESTED: 50,
    CORRELATED: 75,
    ENRICHED: 100,
    INGEST_FAILED: 100,
    CORRELATE_FAILED: 100,
    ENRICH_FAILED: 100,
  };

  const statusColor = s => {
    switch (s) {
      case "ingested":
      case "INGESTED":
        return "var(--amb-lo)";
      case "CORRELATED":
        return "var(--amb)";
      case "ENRICHED":
        return "#3d7a56"; // Green
      case "uploading":
        return "var(--amb)";
      case "error":
      case "INGEST_FAILED":
      case "CORRELATE_FAILED":
      case "ENRICH_FAILED":
        return "#e07070"; // Red
      default:
        return "var(--t3)"; // Grey/default
    }
  };

  const statusLabel = s => {
    switch (s) {
      case "staged":
        return "STAGED";
      case "uploading":
        return "UPLOADING…";
      case "ingested": // Initial status after upload service confirms
        return "✓ UPLOADED";
      case "INGESTED":
        return "✓ INGESTED";
      case "CORRELATED":
        return "✓ CORRELATED";
      case "ENRICHED":
        return "✓ ENRICHED";
      case "INGEST_FAILED":
        return "✗ INGEST FAILED";
      case "CORRELATE_FAILED":
        return "✗ CORRELATE FAILED";
      case "ENRICH_FAILED":
        return "✗ ENRICH FAILED";
      case "error":
      default:
        return "✗ FAILED";
    }
  };

  const addFiles = raw => {
    const valid = Array.from(raw).filter(f =>
      ALLOWED_EXT.some(ext => f.name.toLowerCase().endsWith(ext))
    );
    setFiles(prev => {
      const existing = new Set(prev.map(p => p.file.name));
      const newOnes  = valid.filter(f => !existing.has(f.name));
      return [...prev, ...newOnes.map(f => ({file:f, status:"staged", progress:0, error:null, artifact_id:null, pipeline_stage:null}))];
    });
  };

  const onDrop = e => {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
  };

  const removeFile = name => {
    setFiles(prev => {
      const updatedFiles = prev.filter(p => p.file.name !== name);
      // Clear interval if polling for this file
      const removedFile = prev.find(p => p.file.name === name);
      if (removedFile && removedFile.artifact_id && pollingIntervals.current[removedFile.artifact_id]) {
        clearInterval(pollingIntervals.current[removedFile.artifact_id]);
        delete pollingIntervals.current[removedFile.artifact_id];
      }
      return updatedFiles;
    });
  };

  const startPollingArtifactStatus = useCallback((artifact_id, fileIndex) => {
    if (!artifact_id) return;

    // Clear any existing interval for this artifact_id
    if (pollingIntervals.current[artifact_id]) {
      clearInterval(pollingIntervals.current[artifact_id]);
    }

    const intervalId = setInterval(async () => {
      try {
        const response = await fetch(API + `/v1/artifacts/${artifact_id}`);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        const newStage = data.pipeline_stage;
        const ingestError = data.ingest_error;
        const correlateError = data.correlate_error;
        const enrichTriggerError = data.enrich_trigger_error; // Assuming this might be present
        const correlatedPubFail = data.correlated_pub_fail; // Assuming this might be present

        setFiles(prevFiles => prevFiles.map((f, i) => {
          if (i === fileIndex && f.artifact_id === artifact_id) {
            const newProgress = PIPELINE_STAGE_PROGRESS[newStage] || f.progress;
            return {
              ...f,
              pipeline_stage: newStage,
              status: newStage,
              progress: newProgress,
              ingest_error: ingestError,
              correlate_error: correlateError,
              enrich_trigger_error: enrichTriggerError,
              correlated_pub_fail: correlatedPubFail,
              error: (ingestError || correlateError || enrichTriggerError || correlatedPubFail) || f.error // Prioritize specific errors
            };
          }
          return f;
        }));

        // Stop polling if the artifact has reached a terminal state
        if (newStage === "ENRICHED" || newStage.endsWith("_FAILED")) {
          clearInterval(pollingIntervals.current[artifact_id]);
          delete pollingIntervals.current[artifact_id];
          // Optionally trigger global status refresh
          // if (page === "dash") { // Assuming page state is accessible or passed down
          //   refreshGlobalStatus();
          // }
        }
      } catch (error) {
        console.error(`Error polling artifact ${artifact_id}:`, error);
        setFiles(prevFiles => prevFiles.map((f, i) => {
          if (i === fileIndex && f.artifact_id === artifact_id) {
            return { ...f, status: "error", error: `Polling failed: ${error.message}` };
          }
          return f;
        }));
        clearInterval(pollingIntervals.current[artifact_id]);
        delete pollingIntervals.current[artifact_id];
      }
    }, 5000); // Poll every 5 seconds

    pollingIntervals.current[artifact_id] = intervalId;
  }, []);

  useEffect(() => {
    // Cleanup on component unmount
    return () => {
      for (const artifact_id in pollingIntervals.current) {
        clearInterval(pollingIntervals.current[artifact_id]);
      }
      pollingIntervals.current = {};
    };
  }, []); // Run once on mount, cleanup on unmount

  const uploadFile = async (entry, idx) => {
    setFiles(prev => prev.map((p,i) => i===idx ? {...p, status:"uploading", progress:10} : p));

    try {
      const formData = new FormData();
      formData.append("file", entry.file);

      const tick = setInterval(() => {
        setFiles(prev => prev.map((p,i) => i===idx && p.status==="uploading"
          ? {...p, progress: Math.min(p.progress + 15, 85)} : p));
      }, 400);

      // Try upload with 60s timeout
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 60000);

      let r;
      let errMsg = null;

      try {
        r = await fetch(UPLOAD_API + "/v1/upload", {
          method: "POST",
          body: formData,
          signal: controller.signal,
          headers: { "Accept": "application/json" },
        });
      } catch (fetchErr) {
        clearTimeout(timeoutId);
        clearInterval(tick);
        
        // Network/CORS/timeout error — provide helpful message
        if (fetchErr.name === "AbortError") {
          errMsg = "Upload timeout (>60s). File too large or connection slow.";
        } else if (fetchErr.message.includes("CORS")) {
          errMsg = "CORS blocked. API endpoint may be protected by Cloud IAP.";
        } else if (fetchErr.message.includes("Failed to fetch")) {
          errMsg = "Network error. Check if API endpoint is accessible.";
        } else {
          errMsg = fetchErr.message;
        }

        setFiles(prev => prev.map((p,i) => i===idx
          ? {...p, status:"error", progress:0, error: errMsg}
          : p));
        setGlobalErr(`${entry.file.name}: ${errMsg}`);
        return;
      }

      clearTimeout(timeoutId);
      clearInterval(tick);

      // Parse response
      let d;
      try {
        d = await r.json();
      } catch (parseErr) {
        setFiles(prev => prev.map((p,i) => i===idx
          ? {...p, status:"error", progress:0, error: `HTTP ${r.status}: Invalid response`}
          : p));
        setGlobalErr(`${entry.file.name}: Server returned invalid response (HTTP ${r.status})`);
        return;
      }

      // Check HTTP status
      if (!r.ok) {
        const detail = d.detail || d.message || `HTTP ${r.status}: ${d.error || "Unknown"}`;
        setFiles(prev => prev.map((p,i) => i===idx
          ? {...p, status:"error", progress:0, error: detail}
          : p));
        setGlobalErr(`${entry.file.name}: ${detail}`);
        return;
      }

      // Success or partial success
      const isSuccess = d.status === "ok";
      const isPartial = d.status === "warning" || d.status === "partial";
      const artifact_id = d.artifact_id || "";

      if (isSuccess || isPartial) {
        setFiles(prev => prev.map((p,i) => i===idx
          ? {...p, status:"ingested", progress:PIPELINE_STAGE_PROGRESS.UPLOADED, artifact_id: artifact_id}
          : p));
        startPollingArtifactStatus(artifact_id, idx);
        setGlobalOk(`✓ ${entry.file.name} uploaded. Tracking pipeline progress...`);
        // Trigger cache refresh in query service
        fetch(API + "/v1/cache/refresh", {method:"POST"}).catch(e => console.error("Cache refresh failed:", e));
      } else if (isPartial) {
        setFiles(prev => prev.map((p,i) => i===idx
          ? {...p, status:"ingested", progress:PIPELINE_STAGE_PROGRESS.UPLOADED, artifact_id: artifact_id,
              error: `⚠ ${d.message || "Partial success"}`}
          : p));
        startPollingArtifactStatus(artifact_id, idx);
        setGlobalErr(`${entry.file.name}: ${d.message}`);
        // Trigger cache refresh in query service
        fetch(API + "/v1/cache/refresh", {method:"POST"}).catch(e => console.error("Cache refresh failed:", e));
      }
    } catch(e) {
      clearInterval(tick);
      setFiles(prev => prev.map((p,i) => i===idx
        ? {...p, status:"error", progress:0, error: e.message || "Unknown error"}
        : p));
    }
  };

  const submitAll = async () => {
    const pending = files.filter(p => p.status === "staged");
    if (!pending.length) return;
    setSubmitting(true);
    setGlobalErr(null);
    setGlobalOk(null);

    // Upload in parallel (3 concurrent max)
    const BATCH = 3;
    for (let i = 0; i < files.length; i += BATCH) {
      const batch = files
        .map((f,idx) => ({f,idx}))
        .slice(i, i+BATCH)
        .filter(({f}) => f.status==="staged");
      await Promise.all(batch.map(({f,idx}) => uploadFile(f, idx)));
    }

    setSubmitting(false);
    const failed = files.filter(p => p.status==="error").length;
    const ok     = files.filter(p => p.artifact_id && !p.error).length; // Count successfully tracked artifacts
    if (failed === 0 && ok > 0) setGlobalOk(`${ok} file${ok>1?"s":""} submitted to pipeline. Tracking progress...`);
    else if (failed > 0) setGlobalErr(`${failed} file${failed>1?"s":""} failed. Check errors below.`);
  };
  
  const stagedCount = files.filter(p => p.status==="staged").length;

  return (
    <div className="page">
      <div className="ptitle">Upload Documents</div>
      <div className="psub">STAGE FILES → GCS → INGEST PIPELINE</div>

      {globalOk  && <div className="ok">{globalOk}</div>}
      {globalErr && <div className="err">⚠ {globalErr}</div>}

      {/* Drop Zone */}
      <div
        className={"dz" + (dragging?" over":"")}
        onDragOver={e=>{e.preventDefault();setDragging(true)}}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input ref={inputRef} type="file" multiple accept=".pdf,.docx,.csv"
          style={{display:"none"}} onChange={e => addFiles(e.target.files)}/>
        <div style={{fontSize:26,color:"var(--t3)",marginBottom:11}}>⊕</div>
        <div style={{fontSize:12,color:"var(--t2)",marginBottom:5}}>Drop PDF, DOCX, or CSV files here</div>
        <div style={{fontSize:10,color:"var(--t3)"}}>Click to browse · Triggers INGEST → CORRELATE → ENRICH pipeline</div>
      </div>

      {/* File List */}
      {files.length > 0 && (
        <div className="upload-grid">
          {files.map((entry, i) => (
            <div key={entry.file.name} className="ucard">
              <div className="ufn">{entry.file.name}</div>
              <div style={{fontSize:9,color:"var(--t3)",marginBottom:6}}>
                {(entry.file.size/1024).toFixed(1)} KB · {entry.file.type || "unknown"}
              </div>
              {entry.artifact_id && (
                <div style={{fontSize:9,color:"var(--t3)",marginBottom:4}}>
                  artifact: {entry.artifact_id.length > 20 ? entry.artifact_id.slice(0,20) + "..." : entry.artifact_id}
                </div>
              )}
              {entry.pipeline_stage && entry.pipeline_stage.includes("FAILED") && (
                <div style={{fontSize:9,color:"#e07070",marginBottom:4}}>
                  {entry.pipeline_stage === "INGEST_FAILED" && `Ingest Error: ${entry.ingest_error || 'Unknown'}`}
                  {entry.pipeline_stage === "CORRELATE_FAILED" && `Correlate Error: ${entry.correlate_error || 'Unknown'}`}
                  {entry.pipeline_stage === "CORRELATED_PUB_FAIL" && `Correlate Pub/Sub Error: ${entry.enrich_trigger_error || entry.correlated_pub_fail || 'Unknown'}`}
                  {entry.pipeline_stage === "ENRICH_FAILED" && `Enrich Error: ${entry.enrich_error || 'Unknown'}`}
                </div>
              )}
              {entry.error && (!entry.pipeline_stage || !entry.pipeline_stage.includes("FAILED")) &&
                <div style={{fontSize:9,color:"#e07070",marginBottom:4}}>{entry.error}</div>}
              <div className="ustatus">
                <div className="uprog">
                  <div className="uprog-fill" style={{
                    width: (PIPELINE_STAGE_PROGRESS[entry.pipeline_stage] || entry.progress) + "%",
                    background: statusColor(entry.status)
                  }}/>
                </div>
                <span style={{fontSize:9,color:statusColor(entry.status),minWidth:70}}>
                  {statusLabel(entry.status)}
                </span>
                {entry.status === "staged" && (
                  <span style={{cursor:"pointer",color:"var(--t3)",fontSize:11}}
                    onClick={() => removeFile(entry.file.name)}>✕</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {stagedCount > 0 && (
        <button className="btnp" onClick={submitAll} disabled={submitting}>
          {submitting ? "UPLOADING…" : `SUBMIT ${stagedCount} FILE${stagedCount>1?"S":""} TO PIPELINE`}
        </button>
      )}

      <div style={{marginTop:26}}>
        <div className="sec">PIPELINE FLOW</div>
        <div style={{fontSize:10,color:"var(--t2)",lineHeight:2}}>
          Upload → <span style={{color:"var(--acc)"}}>GCS bucket</span> →
          Pub/Sub notification → <span style={{color:"var(--acc)"}}>INGEST agent</span> (Document AI extraction) →
          <span style={{color:"var(--acc)"}}> CORRELATE agent</span> (Gemini 1M context) →
          <span style={{color:"var(--acc)"}}> ENRICH agent</span> (Vector Search + NER) →
          <span style={{color:"var(--green)"}}> QUERY READY</span>
        </div>
        <div style={{fontSize:9,color:"var(--t3)",marginTop:10}}>
          Note: Full pipeline takes 2–5 min per document depending on size and type.
          Check Artifact Registry for updated pipeline_stage.
        </div>
      </div>
    </div>
  );
}

// ── Nav ────────────────────────────────────────────────────────────────────
const NAV = [
  {id:"dash",      label:"Dashboard",    icon:"◈"},
  {id:"query",     label:"Query Archive", icon:"⌖"},
  {id:"artifacts", label:"Artifacts",    icon:"⊞"},
  {id:"graph",     label:"Rel. Graph",   icon:"⋈"},
  {id:"upload",    label:"Upload",        icon:"⊕"},
];

export default function App() {
  const [page, setPage]   = useState("dash");
  const [status, setStatus] = useState(null);
  const [statusLoading, setSL] = useState(true);

  useEffect(() => {
    const load = () =>
      fetch(API + "/v1/status")
        .then(r => r.json())
        .then(d => setStatus(d))
        .catch(() => {})
        .finally(() => setSL(false));
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, []);

  return (
    <>
      <style>{css}</style>
      <div className="shell">
        <header className="hdr">
          <div className="logo">DDA <span>/ Dark Data Archaeologist</span></div>
          <div className="htag">GCP · GEMINI</div>
          <div className="hstat">
            <div className="dot"/>
            {status
              ? status.total_artifacts + " docs · " + status.relationships + " relations"
              : "Connecting…"}
          </div>
        </header>

        <nav className="side">
          <div className="nlbl">NAVIGATION</div>
          {NAV.map(n => (
            <div key={n.id} className={"nitem"+(page===n.id?" act":"")} onClick={() => setPage(n.id)}>
              <span className="nicon">{n.icon}</span>{n.label}
            </div>
          ))}
          {status && (
            <div className="mstat-wrap">
              <div className="nlbl" style={{padding:0,margin:"0 0 7px"}}>LIVE STATS</div>
              <div className="mrow">Artifacts <span className="mv">{status.total_artifacts}</span></div>
              <div className="mrow">Relations <span className="mv">{status.relationships}</span></div>
              <div className="mrow">Decisions <span className="mv">{status.decisions}</span></div>
            </div>
          )}
        </nav>

        <main className="main">
          {page==="dash"      && <Dashboard status={status} loading={statusLoading}/>}
          {page==="query"     && <QueryPage/>}
          {page==="artifacts" && <ArtifactExplorer page={page}/>}
          {page==="graph"     && <RelGraph page={page}/>}
          {page==="upload"    && <UploadPage/>}
        </main>
      </div>
    </>
  );
}