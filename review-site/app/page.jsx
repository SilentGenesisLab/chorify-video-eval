import { rubric, runs, summary, STAGE_NAMES } from "@/lib/data";

export const dynamic = "force-dynamic";

const pick = (s, name, st) => s?.metrics.find((m) => m.name === name)?.values[st] || "—";

export default function Home() {
  const rb = rubric();
  const all = runs();
  const latest = all[0];
  const s = latest && summary(latest.name);
  return (
    <main className="wrap">
      <div className="head">
        <span className="eyebrow">G1 创意 → G2 分镜 → G3 资产 → G4 成片</span>
        <h1>视频广告四关评审</h1>
        <p className="lede">
          每一关先查红线，再按维度打分，结论由规则算出。评审器用 deepseek-flash 读文字、看图、看成片关键帧，
          技术指标（响度、黑场、冻结帧、分辨率）由程序测量。评审器的可靠性用 420 个带标准答案的构造用例验证。
        </p>
        <div className="row" style={{ marginTop: 8 }}>
          <a className="btn" href="/evaluate" style={{ textDecoration: "none" }}>上传素材评审</a>
          <a className="btn ghost" href="/docs" style={{ textDecoration: "none" }}>查看接口文档</a>
        </div>
      </div>

      <section className="grid4">
        {Object.entries(rb.stages).map(([k, st], i) => (
          <a key={k} className="gate" href={`/rubric#${k}`}>
            <span className="gate-id">G{i + 1} · {STAGE_NAMES[k]}</span>
            <h3>{st.name}</h3>
            <span className="faint">{st.dimensions.length} 个维度 · {st.redlines.length} 条红线</span>
            <ul>{st.dimensions.slice(0, 4).map((d) => <li key={d.id}>{d.name} {Math.round(d.weight * 100)}%</li>)}{st.dimensions.length > 4 && <li>…</li>}</ul>
          </a>
        ))}
      </section>

      {s && (
        <section className="panel">
          <div className="row spread">
            <h2>评审器可靠性 · {latest.name}</h2>
            <a href={`/benchmark?run=${latest.name}`}>完整报告 →</a>
          </div>
          <div className="grid4">
            <div className="stat"><b>{Math.round((s.passed / s.cases) * 100)}%</b><span>用例通过率（{s.passed}/{s.cases}）</span></div>
            <div className="stat"><b>{s.cases}</b><span>已评测用例 · {latest.split === "test" ? "测试集" : "开发集"}</span></div>
            <div className="stat"><b>{s.avg_seconds}s</b><span>单例平均耗时（每例采样 {s.runs} 次）</span></div>
            <div className="stat"><b>{((s.usage.prompt_tokens + s.usage.completion_tokens) / 1e6).toFixed(2)}M</b><span>累计 token</span></div>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>关卡</th><th>红线召回</th><th>误报率</th><th>缺陷灵敏度</th></tr></thead>
              <tbody>
                {s.stages.map((st) => (
                  <tr key={st}>
                    <td>{STAGE_NAMES[st]}</td>
                    <td className="num">{pick(s, "红线召回（命中指定红线）", st)}</td>
                    <td className="num">{pick(s, "误报率（全部无红线用例）", st)}</td>
                    <td className="num">{pick(s, "缺陷灵敏度（目标维度降 ≥1 分）", st)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="grid2">
        <div className="panel">
          <h3>评审器能做什么</h3>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            <li>创意、分镜：红线（极限词、功效断言、未授权 IP、危险行为）和质量维度都可用</li>
            <li>资产：能看图核对角色一致性、品牌规范、授权说明</li>
            <li>成片：程序测量技术硬伤，模型看关键帧和字幕判断叙事、品牌、合规</li>
          </ul>
        </div>
        <div className="panel">
          <h3>必须人工把关的部分</h3>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            <li>模型听不到声音，看不到连续运动：配乐、口播、AI 视频闪烁和穿模需人看</li>
            <li>图片上的小字错字（如“轻氧”写成“青氧”）识别不稳定</li>
            <li>标为“疑似”或多次采样分歧大的项，系统会提示人工复核</li>
          </ul>
        </div>
      </section>
    </main>
  );
}
