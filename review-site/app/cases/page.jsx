import { labels, runs, summary, STAGES, STAGE_NAMES, KIND_NAMES } from "@/lib/data";
import { Verdict } from "../components";

export const dynamic = "force-dynamic";
export const metadata = { title: "用例库 · 视频评审台" };

export default async function Page({ searchParams }) {
  const sp = await searchParams;
  const all = runs();
  const L = labels();
  // 默认合并所有轮次：测试集用例取测试轮次结果，开发集取开发轮次
  const runName = sp.run || "";
  const rowsBy = {};
  for (const r of runName ? [{ name: runName }] : [...all].reverse()) {
    for (const row of summary(r.name)?.rows || []) rowsBy[row.case_id] = { ...row, run: r.name };
  }
  const scenarios = [...new Set(L.map((l) => l.scenario))];
  const variants = [...new Set(L.filter((l) => !sp.stage || l.stage === sp.stage).map((l) => l.variant))].sort();
  const items = L.filter((l) =>
    (!sp.stage || l.stage === sp.stage) && (!sp.scenario || l.scenario === sp.scenario) && (!sp.kind || l.kind === sp.kind) &&
    (!sp.variant || l.variant === sp.variant) && (!sp.split || l.split === sp.split) &&
    (!sp.result || (sp.result === "fail" ? rowsBy[l.case_id]?.pass === false : sp.result === "pass" ? rowsBy[l.case_id]?.pass === true : !rowsBy[l.case_id])));
  const sel = (name, opts, label) => (
    <label>{label}
      <select name={name} defaultValue={sp[name] || ""}>
        <option value="">全部</option>
        {opts.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
      </select>
    </label>
  );
  const industry = Object.fromEntries(L.map((l) => [l.scenario, l.industry]));
  return (
    <main className="wrap">
      <div className="head">
        <span className="eyebrow">dataset/labels.jsonl · {L.length} 例</span>
        <h1>用例库</h1>
        <p className="lede">每个用例都能看到输入材料、标准答案和评审器的完整理由。按“未通过”筛选，可以直接看评审器在哪些地方判断错了。</p>
      </div>
      <form className="filters" method="get">
        {sel("stage", STAGES.map((s) => [s, STAGE_NAMES[s]]), "关卡")}
        {sel("scenario", scenarios.map((s) => [s, `${s} ${industry[s]}`]), "行业样本")}
        {sel("kind", Object.entries(KIND_NAMES), "类型")}
        {sel("variant", variants.map((v) => [v, v]), "变体")}
        {sel("split", [["dev", "开发集"], ["test", "测试集"]], "数据集")}
        {sel("result", [["fail", "未通过"], ["pass", "通过"], ["none", "未评测"]], "评测结果")}
        {sel("run", all.map((r) => [r.name, r.name]), "评测轮次")}
        <button className="btn" type="submit">筛选</button>
        <a href="/cases" className="small">清除</a>
      </form>
      <p className="faint">共 {items.length} 例</p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>用例</th><th>行业</th><th>关卡</th><th>类型</th><th>注入内容</th><th>标准答案</th><th>评审结论</th><th className="n">总分</th><th>是否通过</th></tr></thead>
          <tbody>
            {items.map((l) => {
              const r = rowsBy[l.case_id];
              const exp = l.expect.redlines.length ? `命中 ${l.expect.redlines.join(",")}` : l.expect.target.length ? `${l.expect.target.join(",")} 降分` : l.kind === "invariance" ? "总分不变" : "无红线";
              return (
                <tr key={l.case_id}>
                  <td><a className="mono" href={`/cases/${l.case_id}${r ? `?run=${r.run}` : ""}`}>{l.case_id}</a></td>
                  <td>{l.industry}</td>
                  <td>{STAGE_NAMES[l.stage]}</td>
                  <td><span className="tag">{KIND_NAMES[l.kind]}</span></td>
                  <td style={{ minWidth: 180 }}>{l.description}</td>
                  <td className="small">{exp}</td>
                  <td>{r ? <Verdict v={r.verdict} /> : <span className="faint">未评测</span>}</td>
                  <td className="n">{r?.total ?? ""}</td>
                  <td>{r ? (r.pass ? <span className="check">通过</span> : <span className="cross">未通过</span>) : ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </main>
  );
}
