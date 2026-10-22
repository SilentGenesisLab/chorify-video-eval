"use client";
import { useState } from "react";

const GUIDE = {
  creative: { files: "创意提案（.md / .txt），可多份", accept: ".md,.txt,.markdown", text: "或直接粘贴创意提案", ctx: "brief、品牌规范（可选）" },
  storyboard: { files: "分镜表（.md / .txt / .csv），可附分镜草图图片", accept: ".md,.txt,.csv,.png,.jpg,.jpeg,.webp", text: "或直接粘贴分镜表", ctx: "已通过的创意提案（用于检查创意还原度）" },
  asset: { files: "资产图片（主视觉、角色设定、落版等）+ 资产清单/授权说明", accept: ".png,.jpg,.jpeg,.webp,.md,.txt", text: "资产清单与授权说明（可选）", ctx: "分镜表 + 品牌规范（用于核对一致性与品牌名）" },
  video: { files: "成片视频一个（mp4/mov，≤150MB），可附字幕 .srt", accept: ".mp4,.mov,.webm,.m4v,.srt,.txt", text: "", ctx: "分镜表（用于检查还原度）" },
};

export default function EvaluateForm({ samples, stages }) {
  const [stage, setStage] = useState("storyboard");
  const [main, setMain] = useState(samples.storyboard.main);
  const [ctx, setCtx] = useState(samples.storyboard.context);
  const [isSample, setIsSample] = useState(true);
  const [busy, setBusy] = useState(false);
  const [pct, setPct] = useState(0);
  const [err, setErr] = useState("");
  const g = GUIDE[stage];

  const switchStage = (s) => {
    setStage(s);
    if (isSample || (!main && !ctx)) {
      setMain(samples[s].main);
      setCtx(samples[s].context);
      setIsSample(true);
    }
  };

  const submit = (e) => {
    e.preventDefault();
    setErr("");
    const fd = new FormData(e.currentTarget);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/v1/reviews/${stage}`);
    xhr.setRequestHeader("X-Client", "web");
    xhr.upload.onprogress = (ev) => ev.lengthComputable && setPct(Math.round((ev.loaded / ev.total) * 100));
    xhr.onload = () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch {}
      if (xhr.status >= 200 && xhr.status < 300 && data.id) window.location.href = `/jobs/${data.id}`;
      else { setBusy(false); setErr(data.error?.message || `提交失败（HTTP ${xhr.status}）`); }
    };
    xhr.onerror = () => { setBusy(false); setErr("网络中断，提交失败，请重试"); };
    setBusy(true);
    setPct(0);
    xhr.send(fd);
  };

  return (
    <form className="panel" onSubmit={submit} style={{ gap: 20 }}>
      <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 8 }}>
        <legend style={{ fontWeight: 600, fontSize: 14, marginBottom: 8 }}>评审关卡</legend>
        <div className="seg">
          {Object.entries(stages).map(([k, s], i) => (
            <label key={k}>
              <input type="radio" name="stage_pick" id={`stage-${k}`} checked={stage === k} onChange={() => switchStage(k)} />
              G{i + 1} {s.name.replace(/^G\d\s*/, "")}
            </label>
          ))}
        </div>
        <span className="hint">{stages[stage].dims} 个评分维度，{stages[stage].redlines} 条红线</span>
      </fieldset>

      <label htmlFor="title">名称<span className="hint">方便在评审记录里找到，可不填</span>
        <input type="text" id="title" name="title" placeholder="例如：轻氧 15s 抖音 v2" />
      </label>

      <label htmlFor="files">待评审文件<span className="hint">{g.files}</span>
        <input type="file" id="files" name="files" multiple accept={g.accept} key={stage + "f"} />
      </label>

      {g.text && (
        <label htmlFor="content">{g.text}
          {isSample && main && <span className="hint">已填入示例（测试集 S03 在线英语 App），可直接提交体验，或清空后粘贴你的内容</span>}
          <textarea id="content" name="content" value={main} onChange={(e) => { setMain(e.target.value); setIsSample(false); }} rows={10} />
        </label>
      )}

      <label htmlFor="context">参考材料文件<span className="hint">{g.ctx}</span>
        <input type="file" id="context" name="context" multiple accept=".md,.txt,.csv" key={stage + "c"} />
      </label>
      <label htmlFor="context_text">或粘贴参考材料
        <textarea id="context_text" name="context_text" value={ctx} onChange={(e) => { setCtx(e.target.value); setIsSample(false); }} rows={6} />
      </label>

      {stage === "video" && (
        <>
          <label htmlFor="transcript">台词 / 字幕文本<span className="hint">模型听不到声音，口播和字幕请贴在这里；已上传 .srt 可不填</span>
            <textarea id="transcript" name="transcript" rows={5} />
          </label>
          <label htmlFor="platform_hint">投放平台与规格<span className="hint">留空则按抖音/视频号竖屏 9:16 1080x1920、-14～-16 LUFS 检查</span>
            <input type="text" id="platform_hint" name="platform_hint" placeholder="例如：B站横屏 16:9 1920x1080，响度 -16 LUFS" />
          </label>
        </>
      )}

      <div className="row" style={{ gap: 20 }}>
        <label htmlFor="runs" style={{ flex: "1 1 200px" }}>采样次数
          <select id="runs" name="runs" defaultValue="3">
            <option value="3">3 次（推荐，可发现分歧）</option>
            <option value="1">1 次（更快、更省）</option>
          </select>
        </label>
        <label htmlFor="effort" style={{ flex: "1 1 200px" }}>推理强度
          <select id="effort" name="effort" defaultValue="high">
            <option value="high">high（默认）</option>
            <option value="max">max（更慢）</option>
            <option value="low">low（最快）</option>
          </select>
        </label>
      </div>

      {err && <div className="error" role="alert">{err}</div>}
      {busy && <div className="stack"><span className="faint">上传中 {pct}%</span><div className="meter"><i style={{ width: `${pct}%` }} /></div></div>}
      <div className="row">
        <button className="btn" type="submit" disabled={busy}>{busy ? "提交中…" : "开始评审"}</button>
        <span className="faint">提交后跳转到结果页，可关闭页面稍后在“评审记录”里查看</span>
      </div>
    </form>
  );
}
