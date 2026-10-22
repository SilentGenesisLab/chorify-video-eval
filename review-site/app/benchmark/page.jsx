import { runs, summary, STAGE_NAMES } from "@/lib/data";

export const dynamic = "force-dynamic";
export const metadata = { title: "基准测试 · 视频评审台" };

// 指标的目标线：higher=越高越好
const TARGETS = [
  ["红线召回", 90, true], ["红线检出", 90, true], ["红线用例判驳回", 90, true],
  ["误报率", 10, false], ["缺陷灵敏度", 80, true], ["质量变体总分低于基准", 80, true],
  ["不变性（", 90, true], ["基准判定为通过", 80, true],
];

function Cell({ name, value }) {
  const m = /^(\d+)%/.exec(value || "");
  const t = TARGETS.find(([k]) => name.startsWith(k));
  if (!m || !t) return <span className="num">{value}</span>;
  const p = Number(m[1]);
  const ok = t[2] ? p >= t[1] : p <= t[1];
  const close = t[2] ? p >= t[1] - 15 : p <= t[1] + 15;
  const tone = ok ? "pass" : close ? "warn" : "fail";
  return (
    <div className="metric-cell">
      <span className="num">{value}</span>
      <div className="meter"><i className={tone} style={{ width: `${Math.max(p, 2)}%` }} /></div>
    </div>
  );
}

export default async function Page({ searchParams }) {
  const all = runs();
  const sp = await searchParams;
  const name = sp.run && all.some((r) => r.name === sp.run) ? sp.run : all[0]?.name;
  const s = name && summary(name);
  if (!s) return <main className="wrap"><h1>基准测试</h1><p className="muted">还没有评测结果。</p></main>;
  const isTest = name.startsWith("test");
  const desc = (m) => TARGETS.find(([k]) => m.startsWith(k));
  return (
    <main className="wrap">
      <div className="head">
        <span className="eyebrow">{isTest ? "测试集 S03–S08 · 只用于报告" : "开发集 S01–S02 · 用于调评分标准"}</span>
        <h1>基准测试 · {name}</h1>
        <p className="lede">每个用例的标准答案来自构造：基准样本是合格的，变体只注入一个已知缺陷。看评审器能否命中注入的红线、对应维度是否降分、无关改动下分数是否稳定。</p>
        <nav className="row" aria-label="评测轮次">
          {all.map((r) => (
            <a key={r.name} href={`/benchmark?run=${r.name}`} className={`tag ${r.name === name ? "accent" : ""}`}>
              {r.name} · {r.split === "test" ? "测试集" : "开发集"} · {r.cases} 例
            </a>
          ))}
        </nav>
      </div>

      <section className="grid4">
        <div className="stat"><b>{Math.round((s.passed / s.cases) * 100)}%</b><span>用例通过率（{s.passed}/{s.cases}）</span></div>
        <div className="stat"><b>{s.failures.length}</b><span>未通过的检查项</span></div>
        <div className="stat"><b>{s.avg_seconds}s</b><span>单例平均耗时 · {s.model} × {s.runs}</span></div>
        <div className="stat"><b className="num">{(s.usage.prompt_tokens / 1e6).toFixed(2)}M / {(s.usage.completion_tokens / 1e6).toFixed(2)}M</b><span>输入 / 输出 token</span></div>
      </section>

      <section className="stack">
        <h2>分关卡指标</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th>指标</th><th>目标</th>{s.stages.map((st) => <th key={st}>{STAGE_NAMES[st]}</th>)}</tr></thead>
            <tbody>
              {s.metrics.map((m) => {
                const t = desc(m.name);
                return (
                  <tr key={m.name}>
                    <td style={{ minWidth: 200 }}>{m.name}</td>
                    <td className="faint num">{t ? `${t[2] ? "≥" : "≤"} ${t[1]}%` : m.name.startsWith("不变性变体") ? "≈ 0" : ""}</td>
                    {s.stages.map((st) => <td key={st}><Cell name={m.name} value={m.values[st]} /></td>)}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="faint">资产与成片用例是示意图和动态分镜预演，绝对分数没有参考意义，只看红线和相对变化。</p>
      </section>

      <section className="stack">
        <h2>分变体通过率</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th>关卡</th><th>变体</th><th>注入的缺陷</th><th>通过率</th></tr></thead>
            <tbody>
              {s.variants.map((v) => {
                const p = v.total ? Math.round((v.passed / v.total) * 100) : 0;
                return (
                  <tr key={v.stage + v.variant}>
                    <td>{STAGE_NAMES[v.stage]}</td>
                    <td><a href={`/cases?stage=${v.stage}&variant=${v.variant}&run=${name}`} className="mono">{v.variant}</a></td>
                    <td>{v.description}</td>
                    <td>
                      <div className="metric-cell">
                        <span className="num">{p}% ({v.passed}/{v.total})</span>
                        <div className="meter"><i className={p >= 80 ? "pass" : p >= 50 ? "warn" : "fail"} style={{ width: `${Math.max(p, 2)}%` }} /></div>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="stack">
        <h2>未通过的用例（{s.failures.length}）</h2>
        {s.failures.length ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th>用例</th><th>原因</th></tr></thead>
              <tbody>
                {s.failures.map((f, i) => (
                  <tr key={i}><td><a className="mono" href={`/cases/${f.case_id}?run=${name}`}>{f.case_id}</a></td><td>{f.reason}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="muted">全部通过。</p>}
      </section>
    </main>
  );
}
