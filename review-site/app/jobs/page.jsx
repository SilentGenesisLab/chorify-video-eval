import { listJobs } from "@/lib/jobs";
import { STAGE_NAMES } from "@/lib/data";
import { Verdict } from "../components";
import AutoRefresh from "./refresh";

export const dynamic = "force-dynamic";
export const metadata = { title: "评审记录 · 视频评审台" };

const STATE = { queued: ["排队中", "idle"], running: ["评审中", "warn"], error: ["失败", "fail"] };
const fmt = (ms) => (ms ? new Date(ms).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) : "");

export default function Page() {
  const jobs = listJobs({ limit: 100 }).items;
  const active = jobs.some((j) => j.status.state === "queued" || j.status.state === "running");
  return (
    <main className="wrap">
      <AutoRefresh active={active} />
      <div className="head">
        <h1>评审记录</h1>
        <p className="lede">在线提交的评审任务，最近 100 条。所有人共享同一份记录。</p>
      </div>
      {jobs.length ? (
        <div className="table-wrap">
          <table>
            <thead><tr><th>提交时间</th><th>名称</th><th>关卡</th><th>状态 / 结论</th><th className="n">总分</th><th className="n">采样</th></tr></thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id}>
                  <td className="num small" style={{ whiteSpace: "nowrap" }}>{fmt(j.status.created)}</td>
                  <td><a href={`/jobs/${j.id}`}>{j.job.title}</a></td>
                  <td>{STAGE_NAMES[j.job.stage]}</td>
                  <td>{j.status.state === "done" ? <Verdict v={j.verdict} /> : <span className={`pill ${STATE[j.status.state]?.[1] || "idle"}`}>{STATE[j.status.state]?.[0] || j.status.state}</span>}</td>
                  <td className="n">{j.total ?? ""}</td>
                  <td className="n">{j.job.runs}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="panel">
          <h3>还没有评审记录</h3>
          <p className="muted">到 <a href="/evaluate">在线评审</a> 提交第一份材料。表单里已填好一份分镜示例，直接提交就能看到完整的评审报告。</p>
        </div>
      )}
    </main>
  );
}
