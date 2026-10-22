import path from "node:path";
import { notFound } from "next/navigation";
import { getJob } from "@/lib/jobs";
import { STAGE_NAMES, fileKind, mediaUrl } from "@/lib/data";
import { ReviewResult } from "../../components";
import AutoRefresh from "../refresh";

export const dynamic = "force-dynamic";
export const metadata = { title: "评审结果 · 视频评审台" };

const rel = (id, p) => `jobs/${id}/inputs/${path.basename(p)}`;

function Inputs({ id, files, label }) {
  if (!files?.length) return null;
  return (
    <div className="stack">
      <span className="faint">{label}</span>
      <div className="media-grid">
        {files.map((f) => {
          const u = mediaUrl(rel(id, f));
          const k = fileKind(f);
          const n = path.basename(f).replace(/^(ctx_)?\d\d_/, "");
          if (k === "image") return <figure key={f}><img src={u} alt={n} /><figcaption>{n}</figcaption></figure>;
          if (k === "video") return <figure key={f} style={{ gridColumn: "span 2" }}><video src={u} controls preload="metadata" playsInline style={{ width: "100%", maxWidth: 360 }} /><figcaption>{n}</figcaption></figure>;
          return <figure key={f}><a href={u} target="_blank" className="tag accent">{n}</a></figure>;
        })}
      </div>
    </div>
  );
}

export default async function Page({ params }) {
  const { id } = await params;
  const j = getJob(id);
  if (!j || !j.job) notFound();
  const st = j.status;
  const active = st.state === "queued" || st.state === "running";
  const elapsed = st.started ? Math.round(((st.finished || Date.now()) - st.started) / 1000) : 0;
  return (
    <main className="wrap">
      <AutoRefresh active={active} />
      <div className="head">
        <span className="eyebrow">{STAGE_NAMES[j.job.stage]}评审 · 采样 {j.job.runs} 次 · {j.job.effort}</span>
        <h1>{j.job.title}</h1>
        <div className="row small">
          <a href="/jobs">← 评审记录</a>
          {st.state === "done" && <a href={mediaUrl(`jobs/${id}/report.md`)} target="_blank">Markdown 报告</a>}
          {st.state === "done" && <a href={mediaUrl(`jobs/${id}/result.json`)} target="_blank">原始 JSON</a>}
        </div>
      </div>

      {active && (
        <div className="panel">
          <h3>{st.state === "queued" ? `排队中，前面还有 ${Math.max(st.position - 1, 0)} 个任务` : `评审中，已用时 ${elapsed} 秒`}</h3>
          <div className="progress"><i /></div>
          <p className="faint">单次采样通常 40–90 秒，成片还要先抽帧和测响度。页面会自动刷新，可以关闭稍后再来。</p>
        </div>
      )}
      {st.state === "error" && <div className="error" role="alert">评审失败：{st.error}</div>}

      <details>
        <summary><b>提交的材料</b><span className="faint">{j.job.files.length} 份待评审，{j.job.context.length} 份参考</span></summary>
        <div className="body">
          <Inputs id={id} files={j.job.files} label="待评审" />
          <Inputs id={id} files={j.job.context} label="参考材料" />
          {j.job.transcript && <Inputs id={id} files={[j.job.transcript]} label="台词 / 字幕" />}
        </div>
      </details>

      {j.result && (
        <section className="stack">
          <h2>评审结果 <span className="faint" style={{ fontWeight: 400 }}>用时 {elapsed} 秒</span></h2>
          <ReviewResult ev={j.result} />
        </section>
      )}
    </main>
  );
}
