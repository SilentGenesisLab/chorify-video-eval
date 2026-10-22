// 生成单页静态快照（用于 claude.ai 分享链接）：文档、评分标准、基准结果、用例库；不含图片和视频
// node scripts/snapshot.mjs <输出文件> [在线版地址]
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Marked } from "marked";

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = path.resolve(SITE, "..");
const BENCH = path.join(ROOT, "benchmark");
const out = process.argv[2];
const online = process.argv[3] || "";
const STAGE = { creative: "创意", storyboard: "分镜", asset: "资产", video: "成片" };
const KIND = { base: "基准", redline: "红线", quality: "质量缺陷", invariance: "不变性" };
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const read = (p) => fs.readFileSync(p, "utf8");

function doc(text, prefix) {
  const toc = [];
  const slugs = {};
  let n = 0;
  const m = new Marked({
    gfm: true,
    renderer: {
      heading({ tokens, depth, text: raw }) {
        const id = `${prefix}-${++n}`;
        slugs[raw.replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-|-$/g, "").toLowerCase()] = id;
        if (depth === 2 || depth === 3) toc.push({ id, depth, text: raw.replace(/[*`]/g, "") });
        return `<h${depth} id="${id}">${this.parser.parseInline(tokens)}</h${depth}>`;
      },
    },
  });
  // 文内锚点（与网站同样的 slug 规则）改指向编号 id
  const html = m.parse(text).replace(/href="#([^"]+)"/g, (all, h) => (slugs[decodeURIComponent(h)] ? `href="#${slugs[decodeURIComponent(h)]}"` : all));
  return `<div class="doc-layout"><aside class="toc">${toc.map((t) => `<a href="#${t.id}" class="${t.depth === 3 ? "l3" : ""}">${esc(t.text)}</a>`).join("")}</aside><article class="prose">${html}</article></div>`;
}

const rb = JSON.parse(read(path.join(ROOT, "rubrics.json")));
const labels = read(path.join(BENCH, "dataset", "labels.jsonl")).split("\n").filter(Boolean).map((x) => JSON.parse(x));
const runNames = ["test_v1", "dev_v3"].filter((n) => fs.existsSync(path.join(BENCH, "results", n, "summary.json")));
const sums = Object.fromEntries(runNames.map((n) => [n, JSON.parse(read(path.join(BENCH, "results", n, "summary.json")))]));

// ---------- 评分标准 ----------
const vr = rb.verdict_rules;
const rubricHtml = `
<div class="head"><span class="eyebrow">rubrics.json</span><h1>评分标准</h1>
<p class="lede">每个关卡先查红线，命中任意一条直接驳回；再按维度打 1–5 分，加权得到总分。结论由程序按规则计算，模型只负责给证据和分数。</p></div>
<div class="table-wrap"><table><thead><tr><th>结论</th><th>条件</th></tr></thead><tbody>
<tr><td><span class="pill fail">驳回（命中红线）</span></td><td>任意红线在多数采样中命中</td></tr>
<tr><td><span class="pill pass">通过</span></td><td>加权总分 ≥ ${vr.pass.min_score}，且所有维度 ≥ ${vr.pass.min_dimension} 分</td></tr>
<tr><td><span class="pill warn">修改后通过</span></td><td>加权总分 ≥ ${vr.revise.min_score}，且所有维度 ≥ ${vr.revise.min_dimension} 分</td></tr>
<tr><td><span class="pill fail">驳回</span></td><td>其余情况</td></tr></tbody></table></div>
${Object.entries(rb.stages).map(([k, s], i) => `
<section class="stack" style="gap:14px"><div class="head"><span class="eyebrow">G${i + 1} · ${k}</span><h2>${esc(s.name)}</h2></div>
<div class="panel"><h3>红线（一票否决）</h3><ol style="margin:0;padding-left:22px">${s.redlines.map((r, j) => `<li><span class="num faint">R${j + 1}</span>　${esc(r)}</li>`).join("")}</ol></div>
<div class="table-wrap"><table><thead><tr><th>ID</th><th>维度</th><th class="n">权重</th><th>看什么</th><th>5 分</th><th>2 分</th></tr></thead><tbody>
${s.dimensions.map((d) => `<tr><td class="num">${d.id}</td><td style="white-space:nowrap;font-weight:600">${esc(d.name)}</td><td class="n">${Math.round(d.weight * 100)}%</td><td style="min-width:240px">${esc(d.criteria)}</td><td class="small" style="min-width:180px">${esc(d.anchor_5)}</td><td class="small" style="min-width:180px">${esc(d.anchor_2)}</td></tr>`).join("")}
</tbody></table></div></section>`).join("")}`;

// ---------- 基准结果 ----------
const TARGETS = [["红线召回", 90, true], ["红线检出", 90, true], ["红线用例判驳回", 90, true], ["误报率", 10, false], ["缺陷灵敏度", 80, true], ["质量变体总分低于基准", 80, true], ["不变性（", 90, true], ["基准判定为通过", 80, true]];
const cell = (name, v) => {
  const m = /^(\d+)%/.exec(v || "");
  const t = TARGETS.find(([k]) => name.startsWith(k));
  if (!m || !t) return `<span class="num">${esc(v)}</span>`;
  const p = +m[1];
  const tone = (t[2] ? p >= t[1] : p <= t[1]) ? "pass" : (t[2] ? p >= t[1] - 15 : p <= t[1] + 15) ? "warn" : "fail";
  return `<div class="metric-cell"><span class="num">${esc(v)}</span><div class="meter"><i class="${tone}" style="width:${Math.max(p, 2)}%"></i></div></div>`;
};
const benchHtml = runNames.map((n) => {
  const s = sums[n];
  const isTest = n.startsWith("test");
  return `<div class="run-view stack" data-run="${n}" style="gap:24px" ${isTest ? "" : "hidden"}>
<section class="grid4">
<div class="stat"><b>${Math.round((s.passed / s.cases) * 100)}%</b><span>用例通过率（${s.passed}/${s.cases}）</span></div>
<div class="stat"><b>${s.cases}</b><span>${isTest ? "测试集 S03–S08" : "开发集 S01–S02"}</span></div>
<div class="stat"><b>${s.avg_seconds}s</b><span>单例平均耗时 · ${s.model} × ${s.runs}</span></div>
<div class="stat"><b>${(s.usage.prompt_tokens / 1e6).toFixed(2)}M / ${(s.usage.completion_tokens / 1e6).toFixed(2)}M</b><span>输入 / 输出 token</span></div></section>
<section class="stack"><h2>分关卡指标</h2><div class="table-wrap"><table><thead><tr><th>指标</th><th>目标</th>${s.stages.map((x) => `<th>${STAGE[x]}</th>`).join("")}</tr></thead><tbody>
${s.metrics.map((m) => { const t = TARGETS.find(([k]) => m.name.startsWith(k)); return `<tr><td style="min-width:200px">${esc(m.name)}</td><td class="faint num">${t ? `${t[2] ? "≥" : "≤"} ${t[1]}%` : ""}</td>${s.stages.map((x) => `<td>${cell(m.name, m.values[x])}</td>`).join("")}</tr>`; }).join("")}
</tbody></table></div><p class="faint">资产与成片用例是示意图和动态分镜预演，绝对分数没有参考意义，只看红线和相对变化。</p></section>
<section class="stack"><h2>分变体通过率</h2><div class="table-wrap"><table><thead><tr><th>关卡</th><th>变体</th><th>注入的缺陷</th><th>通过率</th></tr></thead><tbody>
${s.variants.map((v) => { const p = v.total ? Math.round((v.passed / v.total) * 100) : 0; return `<tr><td>${STAGE[v.stage]}</td><td class="mono">${esc(v.variant)}</td><td>${esc(v.description)}</td><td><div class="metric-cell"><span class="num">${p}% (${v.passed}/${v.total})</span><div class="meter"><i class="${p >= 80 ? "pass" : p >= 50 ? "warn" : "fail"}" style="width:${Math.max(p, 2)}%"></i></div></div></td></tr>`; }).join("")}
</tbody></table></div></section>
<section class="stack"><h2>未通过的用例（${s.failures.length}）</h2><div class="table-wrap"><table><thead><tr><th>用例</th><th>原因</th></tr></thead><tbody>
${s.failures.map((f) => `<tr><td><a class="mono" href="#case-${f.case_id}">${f.case_id}</a></td><td>${esc(f.reason)}</td></tr>`).join("")}
</tbody></table></div></section></div>`;
}).join("");

// ---------- 用例数据（精简） ----------
const rowsBy = {};
for (const n of [...runNames].reverse()) for (const r of sums[n].rows) rowsBy[r.case_id] = { ...r, run: n };
const cases = labels.map((l) => {
  const r = rowsBy[l.case_id];
  let res = null;
  if (r) {
    const ev = JSON.parse(read(path.join(BENCH, "results", r.run, `${l.case_id}.json`))).result;
    res = {
      run: r.run, pass: r.pass, verdict: ev.verdict, total: ev.total, dt: r.delta_target, dT: r.delta_total, summary: ev.summary,
      fixes: ev.top_fixes, red: ev.redlines.map((x) => [x.id, x.status, x.status === "未命中" ? "" : x.evidence]),
      dims: ev.dimensions.map((d) => [d.id, d.name, d.mean, d.evidence, d.issues]),
    };
  }
  return { id: l.case_id, sc: l.scenario, ind: l.industry, st: l.stage, kind: l.kind, split: l.split, desc: l.description, base: l.base_case_id, exp: l.expect, files: l.inputs.files.map((f) => path.basename(f)), res };
});
const redText = Object.fromEntries(Object.entries(rb.stages).map(([k, s]) => [k, s.redlines]));

const manual = read(path.join(SITE, "docs", "使用手册.md"));
const apiDoc = read(path.join(SITE, "docs", "API文档.md")).replaceAll("{{BASE_URL}}", (online || "http://localhost:3100").replace(/\/$/, ""));
const framework = read(path.join(ROOT, "视频评审框架.md"));
const css = read(path.join(SITE, "app", "globals.css"));
const t = sums.test_v1;

const html = `<title>视频评审台</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>${css}
body::before { content: ""; position: fixed; inset: 0 0 auto; height: env(safe-area-inset-top, 0px); z-index: 30; background: var(--panel); }
.top { top: env(safe-area-inset-top, 0px); }
.nav button { font: inherit; font-size: 14px; color: var(--muted); padding: 6px 10px; border-radius: var(--radius); border: 0; background: none; cursor: pointer; white-space: nowrap; }
.nav button:hover { background: var(--sunk); color: var(--fg); }
.nav button[aria-current="page"] { color: var(--accent); background: var(--accent-soft); font-weight: 600; }
.case-row { cursor: pointer; }
.back { font: inherit; color: var(--accent); background: none; border: 0; padding: 0; cursor: pointer; }
</style>
<header class="top"><div class="top-in">
<span class="brand"><span class="brand-mark" aria-hidden="true"></span>视频评审台</span>
<nav class="nav" aria-label="主导航">
${[["overview", "概览"], ["benchmark", "基准测试"], ["cases", "用例库"], ["rubric", "评分标准"], ["api", "接口文档"], ["manual", "使用指南"], ["framework", "评审框架"]].map(([k, v]) => `<button type="button" data-tab="${k}">${v}</button>`).join("")}
</nav></div></header>

<main class="wrap" data-view="overview">
<div class="head"><span class="eyebrow">G1 创意 → G2 分镜 → G3 资产 → G4 成片</span><h1>视频广告四关评审</h1>
<p class="lede">每一关先查红线，再按维度打分，结论由规则算出。评审器用 deepseek-flash 读文字、看图、看成片关键帧，技术指标（响度、黑场、冻结帧、分辨率）由程序测量。评审器的可靠性用 420 个带标准答案的构造用例验证。</p></div>
${online ? `<div class="note">这是只读快照，包含文档、评分标准、基准结果和用例的评审理由，不含图片和视频。上传素材做在线评审、调用 HTTP 接口、查看用例的图片和成片，请访问在线版 <b class="mono">${esc(online)}</b>（需要密码）。</div>` : ""}
<section class="grid4">${Object.entries(rb.stages).map(([k, s], i) => `<div class="gate"><span class="gate-id">G${i + 1} · ${STAGE[k]}</span><h3>${esc(s.name)}</h3><span class="faint">${s.dimensions.length} 个维度 · ${s.redlines.length} 条红线</span><ul>${s.dimensions.map((d) => `<li>${esc(d.name)} ${Math.round(d.weight * 100)}%</li>`).join("")}</ul></div>`).join("")}</section>
${t ? `<section class="panel"><h2>评审器可靠性 · 测试集（S03–S08，${t.cases} 例）</h2>
<div class="grid4"><div class="stat"><b>${Math.round((t.passed / t.cases) * 100)}%</b><span>用例通过率（${t.passed}/${t.cases}）</span></div>
<div class="stat"><b>0%</b><span>四关基准样本误报红线</span></div>
<div class="stat"><b>${t.avg_seconds}s</b><span>单例平均耗时</span></div>
<div class="stat"><b>≈ ¥10.8</b><span>测试集 315 例总费用</span></div></div>
<div class="table-wrap"><table><thead><tr><th>关卡</th><th>红线召回</th><th>误报率</th><th>缺陷灵敏度</th><th>不变性</th></tr></thead><tbody>
${t.stages.map((x) => { const g = (n) => t.metrics.find((m) => m.name === n)?.values[x] || "—"; return `<tr><td>${STAGE[x]}</td><td>${cell("红线召回", g("红线召回（命中指定红线）"))}</td><td>${cell("误报率", g("误报率（全部无红线用例）"))}</td><td>${cell("缺陷灵敏度", g("缺陷灵敏度（目标维度降 ≥1 分）"))}</td><td>${cell("不变性（", g("不变性（|Δ总分| ≤ 0.3）"))}</td></tr>`; }).join("")}
</tbody></table></div></section>` : ""}
<section class="grid2">
<div class="panel"><h3>结论</h3><ul style="margin:0;padding-left:20px">
<li>创意、分镜：红线召回 100%，误报 ≤ 3%，可以作为机审第一道关</li>
<li>成片：程序测量的技术硬伤（黑场、冻结、响度、无音轨）全部检出；字幕错别字有漏检</li>
<li>资产：看图核对是短板，主视觉产品名错字、Logo 改色、低分辨率有漏判</li></ul></div>
<div class="panel"><h3>必须人工把关</h3><ul style="margin:0;padding-left:20px">
<li>声音（配乐、口播、BGM 授权）和连续运动（AI 视频闪烁、穿模）</li>
<li>图片上的小字错字</li>
<li>报告标为“疑似”或多次采样分歧大的项</li></ul></div></section>
</main>

<main class="wrap" data-view="benchmark" hidden>
<div class="head"><span class="eyebrow">构造法 · 注入已知缺陷</span><h1>基准测试</h1>
<p class="lede">每个用例的标准答案来自构造：基准样本是合格的，变体只注入一个已知缺陷。看评审器能否命中注入的红线、对应维度是否降分、无关改动下分数是否稳定。</p>
<label class="faint" for="run-pick">评测轮次 <select id="run-pick" style="width:auto">${runNames.map((n) => `<option value="${n}">${n} · ${n.startsWith("test") ? "测试集" : "开发集"} · ${sums[n].cases} 例</option>`).join("")}</select></label></div>
${benchHtml}
</main>

<main class="wrap" data-view="cases" hidden>
<div id="case-list" class="stack" style="gap:20px">
<div class="head"><span class="eyebrow">dataset/labels.jsonl · ${labels.length} 例</span><h1>用例库</h1>
<p class="lede">点击任一用例查看标准答案和评审器的完整理由。筛选“未通过”可以直接看评审器判错的地方。</p></div>
<div class="filters">
<label>关卡<select id="f-stage"><option value="">全部</option>${Object.entries(STAGE).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></label>
<label>行业样本<select id="f-sc"><option value="">全部</option>${[...new Map(labels.map((l) => [l.scenario, l.industry]))].map(([k, v]) => `<option value="${k}">${k} ${v}</option>`).join("")}</select></label>
<label>类型<select id="f-kind"><option value="">全部</option>${Object.entries(KIND).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></label>
<label>评测结果<select id="f-res"><option value="">全部</option><option value="fail">未通过</option><option value="pass">通过</option></select></label>
<label>搜索<input type="text" id="f-q" placeholder="用例号或缺陷描述" style="width:200px"></label>
</div>
<p class="faint" id="case-count"></p>
<div class="table-wrap"><table><thead><tr><th>用例</th><th>行业</th><th>关卡</th><th>类型</th><th>注入内容</th><th>标准答案</th><th>评审结论</th><th class="n">总分</th><th>是否通过</th></tr></thead><tbody id="case-body"></tbody></table></div>
</div>
<div id="case-detail" class="stack" style="gap:20px" hidden></div>
</main>

<main class="wrap" data-view="rubric" hidden>${rubricHtml}</main>
<main class="wrap" data-view="api" hidden>${doc(apiDoc, "a")}</main>
<main class="wrap" data-view="manual" hidden>${doc(manual, "m")}</main>
<main class="wrap" data-view="framework" hidden>${doc(framework, "f")}</main>

<script type="application/json" id="data">${JSON.stringify({ cases, redText, STAGE, KIND }).replace(/</g, "\\u003c")}</script>
<script>
(function () {
  var D = JSON.parse(document.getElementById("data").textContent);
  var byId = {}; D.cases.forEach(function (c) { byId[c.id] = c; });
  var views = document.querySelectorAll("main[data-view]");
  var tabs = document.querySelectorAll(".nav button");
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function tone(v) { v = v || ""; return v.indexOf("驳回") === 0 ? "fail" : v.indexOf("修改") === 0 ? "warn" : v.indexOf("通过") === 0 ? "pass" : "idle"; }
  function show(tab, caseId) {
    views.forEach(function (v) { v.hidden = v.dataset.view !== tab; });
    tabs.forEach(function (b) { if (b.dataset.tab === tab) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
    if (tab === "cases") { if (caseId && byId[caseId]) detail(byId[caseId]); else { document.getElementById("case-detail").hidden = true; document.getElementById("case-list").hidden = false; } }
  }
  function route() {
    var h = location.hash.slice(1);
    if (h.indexOf("case-") === 0) { show("cases", h.slice(5)); window.scrollTo(0, 0); return; }
    var tab = document.querySelector('main[data-view="' + h + '"]') ? h : null;
    if (tab) { show(tab); window.scrollTo(0, 0); return; }
    var el = h && document.getElementById(h);
    if (el) { var v = el.closest("main[data-view]"); show(v.dataset.view); el.scrollIntoView(); return; }
    show("overview");
  }
  tabs.forEach(function (b) { b.addEventListener("click", function () { location.hash = b.dataset.tab; }); });
  window.addEventListener("hashchange", route);

  var pick = document.getElementById("run-pick");
  if (pick) pick.addEventListener("change", function () { document.querySelectorAll(".run-view").forEach(function (v) { v.hidden = v.dataset.run !== pick.value; }); });

  function expText(c) { var e = c.exp; return e.redlines.length ? "命中 " + e.redlines.join(",") : e.target.length ? e.target.join(",") + " 降分" : c.kind === "invariance" ? "总分不变" : "无红线"; }
  var F = ["f-stage", "f-sc", "f-kind", "f-res", "f-q"].map(function (id) { return document.getElementById(id); });
  function list() {
    var st = F[0].value, sc = F[1].value, k = F[2].value, r = F[3].value, q = F[4].value.trim().toLowerCase();
    var rows = D.cases.filter(function (c) {
      return (!st || c.st === st) && (!sc || c.sc === sc) && (!k || c.kind === k) &&
        (!r || (c.res && (r === "fail" ? !c.res.pass : c.res.pass))) && (!q || (c.id + c.desc).toLowerCase().indexOf(q) >= 0);
    });
    document.getElementById("case-count").textContent = "共 " + rows.length + " 例";
    document.getElementById("case-body").innerHTML = rows.map(function (c) {
      var x = c.res;
      return '<tr class="case-row" data-id="' + c.id + '"><td><a class="mono" href="#case-' + c.id + '">' + c.id + "</a></td><td>" + esc(c.ind) + "</td><td>" + D.STAGE[c.st] +
        '</td><td><span class="tag">' + D.KIND[c.kind] + '</span></td><td style="min-width:180px">' + esc(c.desc) + '</td><td class="small">' + expText(c) + "</td><td>" +
        (x ? '<span class="pill ' + tone(x.verdict) + '">' + esc(x.verdict) + "</span>" : '<span class="faint">未评测</span>') + '</td><td class="n">' + (x ? x.total : "") + "</td><td>" +
        (x ? (x.pass ? '<span class="check">通过</span>' : '<span class="cross">未通过</span>') : "") + "</td></tr>";
    }).join("");
  }
  F.forEach(function (f) { f.addEventListener(f.tagName === "INPUT" ? "input" : "change", list); });
  document.getElementById("case-body").addEventListener("click", function (e) { var tr = e.target.closest("tr"); if (tr && e.target.tagName !== "A") location.hash = "case-" + tr.dataset.id; });

  function score(v) {
    if (v == null) return '<span class="faint">—</span>';
    var n = Math.round(v), t = v < 2.5 ? "low" : v < 3.5 ? "mid" : "", s = "";
    for (var i = 1; i <= 5; i++) s += '<i class="' + (i <= n ? "on" : "") + '"></i>';
    return '<span class="row" style="gap:8px"><span class="score ' + t + '">' + s + '</span><span class="num">' + v + "</span></span>";
  }
  function detail(c) {
    document.getElementById("case-list").hidden = true;
    var el = document.getElementById("case-detail"); el.hidden = false;
    var e = c.exp, x = c.res, base = c.base && byId[c.base];
    var exp = [];
    if (e.redlines.length) exp.push("应命中红线 " + e.redlines.join("、"));
    if (e.target.length) exp.push("目标维度 " + e.target.join("、") + " 应比基准降 ≥ 1 分");
    if (e.no_redline) exp.push("不应命中任何红线");
    if (c.kind === "invariance") exp.push("总分与基准相差 ≤ 0.3");
    var reds = D.redText[c.st];
    var h = '<button type="button" class="back" id="back">← 返回用例列表</button>' +
      '<div class="head"><span class="eyebrow">' + c.sc + " " + esc(c.ind) + " · " + D.STAGE[c.st] + " · " + D.KIND[c.kind] + " · " + (c.split === "test" ? "测试集" : "开发集") + "</span>" +
      '<h1 class="mono" style="font-size:22px">' + c.id + '</h1><p class="lede">' + esc(c.desc) + "</p>" +
      (base ? '<p class="small">对照基准 <a href="#case-' + base.id + '">' + base.id + "</a></p>" : "") + "</div>" +
      '<section class="grid2"><div class="panel"><h3>标准答案</h3><ul style="margin:0;padding-left:20px">' + exp.map(function (t) { return "<li>" + t + "</li>"; }).join("") + "</ul>" +
      '<p class="faint">评审材料：' + c.files.map(esc).join("、") + "</p></div>" +
      '<div class="panel"><h3>评审器是否答对</h3>' + (x ? "<p>" + (x.pass ? '<span class="check">通过</span>' : '<span class="cross">未通过</span>') + '　<span class="faint">评测轮次 ' + x.run + "</span></p>" +
      '<ul class="small" style="margin:0;padding-left:20px">' + (x.dt !== "" ? '<li>目标维度变化 <span class="num">' + (x.dt > 0 ? "+" : "") + x.dt + "</span></li>" : "") +
      (x.dT !== "" ? '<li>总分变化 <span class="num">' + (x.dT > 0 ? "+" : "") + x.dT + "</span></li>" : "") + "</ul>" : '<p class="muted">尚未评测</p>') + "</div></section>";
    if (x) {
      h += '<div class="panel"><div class="row" style="gap:14px"><span class="pill ' + tone(x.verdict) + '">' + esc(x.verdict) + '</span><span class="num" style="font-size:22px;font-weight:600">' + x.total + '</span><span class="faint">/ 5 加权总分</span></div><p>' + esc(x.summary) + "</p>" +
        (x.fixes && x.fixes.length ? '<h3>优先修改</h3><ol style="margin:0;padding-left:20px">' + x.fixes.map(function (f) { return "<li>" + esc(f) + "</li>"; }).join("") + "</ol>" : "") + "</div>";
      h += '<h3>红线检查</h3><div class="table-wrap"><table><thead><tr><th>ID</th><th>红线</th><th>结果</th><th>标准答案</th><th>证据</th></tr></thead><tbody>' +
        x.red.map(function (r, i) {
          var should = e.redlines.indexOf(r[0]) >= 0;
          return '<tr><td class="num">' + r[0] + '</td><td style="min-width:160px">' + esc(reds[i]) + '</td><td><span class="pill ' + (r[1] === "命中" ? "fail" : r[1].indexOf("疑似") === 0 ? "warn" : "idle") + '">' + esc(r[1]) + "</span></td><td>" +
            (should ? '<span class="' + (r[1] === "命中" ? "check" : "cross") + '">应命中</span>' : '<span class="faint">—</span>') + '</td><td class="small" style="min-width:240px">' + (esc(r[2]) || '<span class="faint">—</span>') + "</td></tr>";
        }).join("") + "</tbody></table></div>";
      h += '<h3>维度评分</h3><div class="stack">' + x.dims.map(function (d) {
        var tgt = e.target.indexOf(d[0]) >= 0;
        var bd = base && base.res && base.res.dims.filter(function (b) { return b[0] === d[0]; })[0];
        return "<details" + (tgt ? " open" : "") + '><summary><span class="num faint" style="width:26px">' + d[0] + '</span><span style="flex:1 1 160px;font-weight:600">' + esc(d[1]) +
          (tgt ? ' <span class="tag accent">注入缺陷的目标维度</span>' : "") + "</span>" + score(d[2]) + (bd ? '<span class="faint num">基准 ' + bd[2] + "</span>" : "") + "</summary>" +
          '<div class="body"><p><b>证据</b>：' + esc(d[3]) + "</p>" + (d[4] && d[4].length ? "<div><b>问题</b><ul>" + d[4].map(function (i) { return "<li>" + esc(i) + "</li>"; }).join("") + "</ul></div>" : "") + "</div></details>";
      }).join("") + "</div>";
    }
    el.innerHTML = h;
    document.getElementById("back").addEventListener("click", function () { location.hash = "cases"; });
  }
  list();
  route();
})();
</script>`;

// 模型输出里偶有 U+FFFD 乱码字符，直接去掉
fs.writeFileSync(out, html.replace(/\uFFFD/g, ""));
console.log(`${out} ${(html.length / 1024).toFixed(0)} KB`);
