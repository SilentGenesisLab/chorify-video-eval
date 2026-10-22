import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { BENCH, STAGES, labels } from "./data";
import { PYTHON } from "./jobs";
import { ApiError } from "./api";

// 基准测试轮次：results/<name>/ 下的 run_spec.json（参数）、run_status.json（状态）、summary.json（指标）
const RESULTS = path.join(BENCH, "results");
const COST_PER_SAMPLE = 0.035; // 元，按 test_v1 实测（315 例 ≈ ¥10.8）估算
const g = globalThis;
g.__benchRun ||= { name: null };

const read = (p) => {
  try {
    return JSON.parse(fs.readFileSync(p, "utf8"));
  } catch {
    return null;
  }
};
const alive = (pid) => {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
};

export function filterLabels(spec) {
  return labels().filter((l) =>
    (!spec.split || l.split === spec.split) && (!spec.stages?.length || spec.stages.includes(l.stage)) &&
    (!spec.scenarios?.length || spec.scenarios.includes(l.scenario)) && (!spec.variants?.length || spec.variants.includes(l.variant)));
}

function status(name) {
  const dir = path.join(RESULTS, name);
  const st = read(path.join(dir, "run_status.json"));
  const hasSummary = fs.existsSync(path.join(dir, "summary.json"));
  if (st?.state === "running" && !alive(st.pid)) return { ...st, state: "interrupted" };
  if (st) return st;
  return { state: hasSummary ? "done" : "unknown" };
}

export function runInfo(name, { rows = false } = {}) {
  if (!/^[A-Za-z0-9_-]{1,40}$/.test(name || "")) return null;
  const dir = path.join(RESULTS, name);
  if (!fs.existsSync(dir)) return null;
  const spec = read(path.join(dir, "run_spec.json"));
  const done = fs.readdirSync(dir).filter((f) => /^S\d+_.+\.json$/.test(f)).length;
  const total = spec?.total ?? null;
  const s = read(path.join(dir, "summary.json"));
  const st = status(name);
  let summary = null;
  if (s) {
    const { rows: r, ...rest } = s;
    summary = { ...rest, pass_rate: s.cases ? +(s.passed / s.cases).toFixed(4) : null, ...(rows ? { rows: r } : {}) };
  }
  return {
    name, split: spec?.split || (name.startsWith("test") ? "test" : name.startsWith("dev") ? "dev" : null),
    status: st.state, started_at: st.started ? new Date(st.started).toISOString() : null,
    finished_at: st.finished ? new Date(st.finished).toISOString() : null, error: st.error || null,
    progress: { done, total }, spec, summary,
  };
}

export function listRuns() {
  if (!fs.existsSync(RESULTS)) return [];
  return fs
    .readdirSync(RESULTS)
    .filter((n) => fs.statSync(path.join(RESULTS, n)).isDirectory())
    .map((n) => runInfo(n))
    .filter((r) => r && (r.summary || r.spec))
    .map(({ summary, ...r }) => ({ ...r, cases: summary?.cases ?? null, passed: summary?.passed ?? null, pass_rate: summary?.pass_rate ?? null }))
    .sort((a, b) => (b.started_at || "").localeCompare(a.started_at || "") || a.name.localeCompare(b.name));
}

export function startRun(body) {
  const name = body.name;
  if (!/^[A-Za-z0-9_-]{1,40}$/.test(name || "")) throw new ApiError(400, "invalid_name", "name 只能包含字母、数字、下划线和连字符，最长 40");
  const arr = (k) => {
    const v = body[k];
    if (v == null) return [];
    if (!Array.isArray(v)) throw new ApiError(400, "invalid_body", `${k} 必须是数组`);
    return v.map(String);
  };
  const spec = {
    split: body.split ?? null, stages: arr("stages"), scenarios: arr("scenarios"), variants: arr("variants"),
    runs: body.runs ?? 1, workers: body.workers ?? 4, effort: body.effort ?? "high",
  };
  if (spec.split && !["dev", "test"].includes(spec.split)) throw new ApiError(400, "invalid_split", "split 必须是 dev 或 test");
  if (spec.stages.some((s) => !STAGES.includes(s))) throw new ApiError(400, "invalid_stage", `stages 只能包含 ${STAGES.join(" / ")}`);
  if (![1, 2, 3].includes(spec.runs)) throw new ApiError(400, "invalid_runs", "runs 必须是 1、2 或 3");
  if (!Number.isInteger(spec.workers) || spec.workers < 1 || spec.workers > 10) throw new ApiError(400, "invalid_workers", "workers 取 1–10");
  if (!["low", "high", "max"].includes(spec.effort)) throw new ApiError(400, "invalid_effort", "effort 必须是 low / high / max");
  const cases = filterLabels(spec);
  if (!cases.length) throw new ApiError(400, "no_cases", "筛选条件下没有用例");
  const dir = path.join(RESULTS, name);
  const cached = fs.existsSync(dir) ? cases.filter((l) => fs.existsSync(path.join(dir, `${l.case_id}.json`))).length : 0;
  const todo = cases.length - cached;
  const estimate = { cases: cases.length, cached, to_run: todo, samples: todo * spec.runs, estimated_cost_cny: +(todo * spec.runs * COST_PER_SAMPLE).toFixed(2) };
  if (body.dry_run) return { dry_run: true, name, spec, estimate };

  const cur = g.__benchRun.name;
  if (cur && status(cur).state === "running") throw new ApiError(409, "run_in_progress", `已有基准测试 ${cur} 在运行，请等待完成`, { running: cur });
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "run_spec.json"), JSON.stringify({ ...spec, total: cases.length, created: Date.now() }, null, 1));
  const args = [path.join(BENCH, "run_benchmark.py"), "--name", name, "--runs", String(spec.runs), "--workers", String(spec.workers), "--effort", spec.effort];
  if (spec.split) args.push("--split", spec.split);
  if (spec.stages.length) args.push("--stages", ...spec.stages);
  if (spec.scenarios.length) args.push("--scenarios", ...spec.scenarios);
  if (spec.variants.length) args.push("--variants", ...spec.variants);
  const log = fs.openSync(path.join(dir, "run.log"), "a");
  const p = spawn(PYTHON, args, { cwd: BENCH, stdio: ["ignore", log, log] });
  const started = Date.now();
  fs.writeFileSync(path.join(dir, "run_status.json"), JSON.stringify({ state: "running", pid: p.pid, started }));
  g.__benchRun.name = name;
  p.on("exit", (code) => {
    fs.closeSync(log);
    const tail = fs.readFileSync(path.join(dir, "run.log"), "utf8").trim().split("\n").slice(-3).join(" ").slice(0, 400);
    fs.writeFileSync(path.join(dir, "run_status.json"), JSON.stringify({
      state: code === 0 ? "done" : "error", pid: p.pid, started, finished: Date.now(), exit_code: code, ...(code === 0 ? {} : { error: tail }),
    }));
  });
  return { dry_run: false, name, spec, estimate };
}
