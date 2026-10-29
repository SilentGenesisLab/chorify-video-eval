import { rubric } from "@/lib/data";

export const dynamic = "force-dynamic";
export const metadata = { title: "评分标准 · 视频评审台" };

export default function Page() {
  const rb = rubric();
  const vr = rb.verdict_rules;
  const gates = Object.entries(rb.stages);
  return (
    <main className="wrap">
      <div className="head">
        <span className="eyebrow">rubrics.json</span>
        <h1>评分标准</h1>
        <p className="lede">评审器和人工评审使用同一套标准。每个关卡先查红线，命中任意一条直接驳回；再按维度打 1–5 分，加权得到总分。结论由程序按规则计算，模型只负责给证据和分数。</p>
      </div>

      <div className="panel">
        <h2>结论规则</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th>结论</th><th>条件</th></tr></thead>
            <tbody>
              <tr><td><span className="pill fail">驳回（命中红线）</span></td><td>任意红线在多数采样中命中</td></tr>
              <tr><td><span className="pill pass">通过</span></td><td>加权总分 ≥ {vr.pass.min_score}，且所有维度 ≥ {vr.pass.min_dimension} 分</td></tr>
              <tr><td><span className="pill warn">修改后通过</span></td><td>加权总分 ≥ {vr.revise.min_score}，且所有维度 ≥ {vr.revise.min_dimension} 分</td></tr>
              <tr><td><span className="pill fail">驳回</span></td><td>其余情况</td></tr>
            </tbody>
          </table>
        </div>
        <p className="faint">红线只在少数采样中命中时标为“疑似”，不直接驳回，转人工复核。以下也转人工：红线命中、维度分数缺失或无效、多次采样分差 ≥ 2 分、成片的画面质量与声音质量、机审驳回（转法务 / 品牌复核）。</p>
      </div>

      <nav className="row" aria-label="关卡">
        {gates.map(([k, s], i) => <a key={k} className="tag accent" href={`#${k}`}>G{i + 1} {s.name}</a>)}
      </nav>

      {gates.map(([k, s], i) => (
        <section key={k} id={k} className="stack" style={{ gap: 14 }}>
          <div className="head">
            <span className="eyebrow">G{i + 1} · {k}</span>
            <h2>{s.name}</h2>
            {s.description && <p className="lede">{s.description}</p>}
          </div>
          <div className="panel">
            <h3>红线（一票否决）</h3>
            <ol style={{ margin: 0, paddingLeft: 22 }}>
              {s.redlines.map((r, j) => <li key={j}><span className="num faint">R{j + 1}</span>　{r}</li>)}
            </ol>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>ID</th><th>维度</th><th className="n">权重</th><th>看什么</th><th>5 分</th><th>2 分</th></tr></thead>
              <tbody>
                {s.dimensions.map((d) => (
                  <tr key={d.id}>
                    <td className="num">{d.id}</td>
                    <td style={{ whiteSpace: "nowrap", fontWeight: 600 }}>{d.name}</td>
                    <td className="n">{Math.round(d.weight * 100)}%</td>
                    <td style={{ minWidth: 240 }}>{d.criteria}</td>
                    <td style={{ minWidth: 180 }} className="small">{d.anchor_5}</td>
                    <td style={{ minWidth: 180 }} className="small">{d.anchor_2}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </main>
  );
}
