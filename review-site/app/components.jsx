// 无状态展示组件，服务端页面和客户端页面共用

export function verdictTone(v = "") {
  if (v.startsWith("驳回")) return "fail";
  if (v.startsWith("修改")) return "warn";
  if (v.startsWith("通过")) return "pass";
  return "idle";
}

export function Verdict({ v }) {
  return <span className={`pill ${verdictTone(v)}`}>{v || "—"}</span>;
}

export function Score({ value }) {
  if (value == null) return <span className="faint">—</span>;
  const n = Math.round(value);
  const tone = value < 2.5 ? "low" : value < 3.5 ? "mid" : "";
  return (
    <span className="row" style={{ gap: 8 }}>
      <span className={`score ${tone}`} aria-label={`${value} 分`}>
        {[1, 2, 3, 4, 5].map((i) => <i key={i} className={i <= n ? "on" : ""} />)}
      </span>
      <span className="num">{value}</span>
    </span>
  );
}

const fmtTech = (v) => (Array.isArray(v) ? (v.length ? v.join("，") : "无") : v === null || v === "" ? "无" : String(v));

// 一次评审结果：结论 → 红线 → 维度 → 修改建议
export function ReviewResult({ ev, expect }) {
  const r = ev.result;
  const hit = (id) => r.redlines.find((x) => x.id === id)?.status;
  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="panel">
        <div className="row spread">
          <div className="row" style={{ gap: 14 }}>
            <Verdict v={r.verdict} />
            <span className="num" style={{ fontSize: 22, fontWeight: 600 }}>{r.total}</span>
            <span className="faint">/ 5 加权总分 · 最低维度 {r.min_dimension}</span>
          </div>
          <span className="faint">
            {r.stage} · 采样 {ev.raw_runs?.length || 1} 次{ev.usage ? ` · token ${ev.usage.prompt_tokens?.toLocaleString()} / ${ev.usage.completion_tokens?.toLocaleString()}` : ""}
          </span>
        </div>
        {r.summary && <p>{r.summary}</p>}
        {r.needs_human_review?.length > 0 && (
          <div className="note">需人工复核：{r.needs_human_review.map((k) => (r.review_reasons?.[k] ? `${k}（${r.review_reasons[k]}）` : k)).join("；")}</div>
        )}
      </div>

      {r.top_fixes?.length > 0 && (
        <div className="panel">
          <h3>优先修改</h3>
          <ol style={{ margin: 0, paddingLeft: 20 }}>{r.top_fixes.map((x, i) => <li key={i}>{x}</li>)}</ol>
          {r.highlights?.length > 0 && (
            <>
              <h3>亮点</h3>
              <ul style={{ margin: 0, paddingLeft: 20 }}>{r.highlights.map((x, i) => <li key={i}>{x}</li>)}</ul>
            </>
          )}
        </div>
      )}

      {ev.tech && (
        <div className="stack">
          <h3>技术参数（程序测量）</h3>
          <div className="table-wrap">
            <table>
              <tbody>
                {Object.entries(ev.tech).map(([k, v]) => (
                  <tr key={k}><th style={{ width: 160 }}>{k}</th><td className="num" style={{ textAlign: "left" }}>{fmtTech(v)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="stack">
        <h3>红线检查</h3>
        <div className="table-wrap">
          <table>
            <thead><tr><th>ID</th><th>红线</th><th>结果</th>{expect && <th>标准答案</th>}<th>证据 / 疑点</th></tr></thead>
            <tbody>
              {r.redlines.map((x) => {
                const should = expect?.redlines?.includes(x.id);
                return (
                  <tr key={x.id}>
                    <td className="num">{x.id}</td>
                    <td style={{ minWidth: 160 }}>{x.text}</td>
                    <td><span className={`pill ${x.status === "命中" ? "fail" : x.status.startsWith("疑似") ? "warn" : "idle"}`}>{x.status} {x.hits}</span></td>
                    {expect && <td>{should ? <span className={hit(x.id) === "命中" ? "check" : "cross"}>应命中</span> : <span className="faint">—</span>}</td>}
                    <td className="small" style={{ minWidth: 260 }}>{x.evidence || <span className="faint">—</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="stack">
        <h3>维度评分</h3>
        {r.dimensions.map((d) => (
          <details key={d.id}>
            <summary>
              <span className="num faint" style={{ width: 26 }}>{d.id}</span>
              <span style={{ flex: "1 1 160px", fontWeight: 600 }}>
                {d.name} <span className="faint">权重 {Math.round(d.weight * 100)}%</span>
                {expect?.target?.includes(d.id) && <span className="tag accent" style={{ marginLeft: 8 }}>注入缺陷的目标维度</span>}
              </span>
              <Score value={d.mean} />
              {d.scores?.length > 1 && <span className="faint num">各次 {d.scores.join(" / ")}</span>}
            </summary>
            <div className="body">
              <p className="faint">评分标准：{d.criteria}（5 分：{d.anchor_5}；2 分：{d.anchor_2}）</p>
              <p><b>证据</b>：{d.evidence}</p>
              {d.issues?.length > 0 && (<div><b>问题</b><ul>{d.issues.map((x, i) => <li key={i}>{x}</li>)}</ul></div>)}
              {d.suggestions?.length > 0 && (<div><b>建议</b><ul>{d.suggestions.map((x, i) => <li key={i}>{x}</li>)}</ul></div>)}
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}
