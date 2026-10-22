import path from "node:path";
import { notFound } from "next/navigation";
import { BENCH, label, findResult, caseRow, readText, md, mediaUrl, fileKind, STAGE_NAMES, KIND_NAMES } from "@/lib/data";
import { ReviewResult } from "../../components";

export const dynamic = "force-dynamic";

function Material({ rel }) {
  const name = path.basename(rel);
  const kind = fileKind(rel);
  const url = mediaUrl(rel);
  if (kind === "image") return <figure><img src={url} alt={name} loading="lazy" /><figcaption>{name}</figcaption></figure>;
  if (kind === "video") return null;
  const text = readText(path.join(BENCH, rel)) || "";
  return (
    <div className="stack" style={{ gridColumn: "1 / -1" }}>
      <span className="faint mono">{name}</span>
      {rel.endsWith(".md") ? <div className="textfile prose" dangerouslySetInnerHTML={{ __html: md(text) }} /> : <pre className="textfile">{text}</pre>}
    </div>
  );
}

export async function generateMetadata({ params }) {
  return { title: `${(await params).id} · 用例库` };
}

export default async function Page({ params, searchParams }) {
  const { id } = await params;
  const sp = await searchParams;
  const l = label(id);
  if (!l) notFound();
  const ev = findResult(id, sp.run);
  const row = ev && caseRow(ev.run, id);
  const base = l.base_case_id && findResult(l.base_case_id, ev?.run);
  const files = l.inputs.files;
  const videos = files.filter((f) => fileKind(f) === "video");
  const expect = l.expect;
  const expText = [
    expect.redlines.length && `应命中红线 ${expect.redlines.join("、")}`,
    expect.target.length && `目标维度 ${expect.target.join("、")} 应比基准降 ≥ 1 分`,
    expect.no_redline && "不应命中任何红线",
    l.kind === "invariance" && "总分与基准相差 ≤ 0.3",
  ].filter(Boolean);
  const wide = /1920x1080|16:9/.test(JSON.stringify(l.inputs.platform_hint || ""));
  return (
    <main className="wrap">
      <div className="head">
        <span className="eyebrow">{l.scenario} {l.industry} · {STAGE_NAMES[l.stage]} · {KIND_NAMES[l.kind]} · {l.split === "test" ? "测试集" : "开发集"}</span>
        <h1 className="mono" style={{ fontSize: 22 }}>{id}</h1>
        <p className="lede">{l.description}</p>
        <div className="row small">
          <a href={`/cases?stage=${l.stage}&scenario=${l.scenario}`}>同行业同关卡的其他用例</a>
          {l.base_case_id && <a href={`/cases/${l.base_case_id}${ev ? `?run=${ev.run}` : ""}`}>对照基准 {l.base_case_id}</a>}
        </div>
      </div>

      <section className="grid2">
        <div className="panel">
          <h3>标准答案</h3>
          <ul style={{ margin: 0, paddingLeft: 20 }}>{expText.map((t, i) => <li key={i}>{t}</li>)}</ul>
          <p className="faint">来源：{l.label_source}</p>
        </div>
        <div className="panel">
          <h3>评审器是否答对</h3>
          {row ? (
            <>
              <p>{row.pass ? <span className="check">通过</span> : <span className="cross">未通过</span>}　<span className="faint">评测轮次 {ev.run}</span></p>
              <ul style={{ margin: 0, paddingLeft: 20 }} className="small">
                <li>命中红线：{row.hits || "无"}</li>
                {row.delta_target !== "" && <li>目标维度变化：<span className="num">{row.delta_target > 0 ? "+" : ""}{row.delta_target}</span>（基准 {base?.result?.dimensions.find((d) => d.id === expect.target[0])?.mean}）</li>}
                {row.delta_total !== "" && <li>总分变化：<span className="num">{row.delta_total > 0 ? "+" : ""}{row.delta_total}</span>（基准 {base?.result?.total}）</li>}
              </ul>
            </>
          ) : <p className="muted">这个用例还没有评测结果。</p>}
        </div>
      </section>

      <section className="stack">
        <h2>待评审材料</h2>
        {videos.map((v) => (
          <div key={v} className={`video-box ${wide ? "wide" : ""}`}>
            <video src={mediaUrl(v)} controls preload="metadata" playsInline />
          </div>
        ))}
        <div className="media-grid">{files.filter((f) => fileKind(f) !== "video").map((f) => <Material key={f} rel={f} />)}</div>
        {l.inputs.transcript && <Material rel={l.inputs.transcript} />}
        {l.inputs.context?.length > 0 && (
          <details>
            <summary><b>参考材料</b><span className="faint">前序关卡已通过的内容，评审器用来对照还原度（{l.inputs.context.length} 份）</span></summary>
            <div className="body"><div className="media-grid">{l.inputs.context.map((c) => <Material key={c} rel={c} />)}</div></div>
          </details>
        )}
      </section>

      <section className="stack">
        <h2>评审器的判断</h2>
        {ev ? <ReviewResult ev={ev} expect={expect} /> : <p className="muted">尚未评测。</p>}
      </section>
    </main>
  );
}
