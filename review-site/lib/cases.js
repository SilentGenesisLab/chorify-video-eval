import path from "node:path";
import { labels, label, runs, summary, findResult, caseRow, readText, BENCH, fileKind } from "./data";
import { fileUrl, serializeResult } from "./api";

// 用例库查询：标签 + 评测结果（默认合并所有轮次，测试集轮次优先）
function rowsIndex(run) {
  const idx = {};
  for (const r of run ? [{ name: run }] : [...runs()].reverse()) {
    for (const row of summary(r.name)?.rows || []) idx[row.case_id] = { ...row, run: r.name };
  }
  return idx;
}

const brief = (l, row) => ({
  id: l.case_id, scenario: l.scenario, industry: l.industry, split: l.split, stage: l.stage, kind: l.kind,
  variant: l.variant, description: l.description, base_case_id: l.base_case_id, expect: l.expect,
  evaluation: row ? {
    run: row.run, passed: row.pass, verdict: row.verdict, total: row.total,
    redlines_hit: row.hits ? row.hits.split(",") : [],
    delta_target: row.delta_target === "" ? null : row.delta_target, delta_total: row.delta_total === "" ? null : row.delta_total,
  } : null,
});

export function queryCases(sp) {
  const run = sp.get("run") || "";
  const idx = rowsIndex(run);
  const f = (k) => sp.get(k) || "";
  const result = f("result");
  const q = f("q").toLowerCase();
  const items = labels().filter((l) => {
    const row = idx[l.case_id];
    return (!f("stage") || l.stage === f("stage")) && (!f("scenario") || l.scenario === f("scenario")) &&
      (!f("kind") || l.kind === f("kind")) && (!f("variant") || l.variant === f("variant")) && (!f("split") || l.split === f("split")) &&
      (!result || (result === "pass" ? row?.pass === true : result === "fail" ? row?.pass === false : result === "none" ? !row : true)) &&
      (!q || (l.case_id + l.description).toLowerCase().includes(q));
  });
  return { items: items.map((l) => brief(l, idx[l.case_id])), total: items.length };
}

export function getCase(id, run, base, { raw = false, text = true } = {}) {
  const l = label(id);
  if (!l) return null;
  const ev = findResult(id, run);
  const row = ev && caseRow(ev.run, id);
  const file = (rel) => {
    const kind = fileKind(rel);
    const out = { name: path.basename(rel), kind, url: fileUrl(base, rel) };
    if (kind === "text" && text) out.text = readText(path.join(BENCH, rel));
    return out;
  };
  return {
    ...brief(l, row ? { ...row, run: ev.run } : null),
    label_source: l.label_source,
    inputs: {
      files: l.inputs.files.map(file), context: (l.inputs.context || []).map(file),
      transcript: l.inputs.transcript ? file(l.inputs.transcript) : null, platform_hint: l.inputs.platform_hint || null,
    },
    result: ev ? serializeResult(ev, { raw }) : null,
  };
}
