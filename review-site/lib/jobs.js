import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { spawn } from "node:child_process";
import { ROOT, SITE, STAGES, reviewEnv } from "./data";
import { ApiError, serializeReview } from "./api";

// 在线评审任务：每个任务一个目录，状态落盘；进程内排队，同一时间只跑 MAX_RUNNING 个（每个约 100MB）
export const JOBS = path.join(SITE, "data", "jobs");
const MAX_RUNNING = Number(process.env.MAX_RUNNING || 2);
export const PYTHON = process.env.PYTHON || path.join(ROOT, ".venv", "bin", "python");
export const MAX_BYTES = 150 * 1024 * 1024;
const VIDEO_RE = /\.(mp4|mov|webm|m4v|mkv)$/i;
const ALLOWED_EXT = /\.(md|markdown|txt|csv|srt|json|png|jpe?g|webp|gif|mp4|mov|webm|m4v|mkv)$/i;

const g = globalThis;
g.__reviewQueue ||= { queue: [], running: new Set(), recovered: false };
const Q = g.__reviewQueue;

const write = (dir, name, obj) => fs.writeFileSync(path.join(dir, name), JSON.stringify(obj, null, 1));
const read = (dir, name) => {
  try {
    return JSON.parse(fs.readFileSync(path.join(dir, name), "utf8"));
  } catch {
    return null;
  }
};

export const jobDir = (id) => {
  if (!/^[a-z0-9-]+$/.test(id || "")) return null;
  const d = path.join(JOBS, id);
  return fs.existsSync(d) ? d : null;
};

function recover() {
  if (Q.recovered) return;
  Q.recovered = true;
  fs.mkdirSync(JOBS, { recursive: true });
  for (const id of fs.readdirSync(JOBS)) {
    const st = read(path.join(JOBS, id), "status.json");
    if (st && (st.state === "running" || st.state === "queued")) {
      write(path.join(JOBS, id), "status.json", { ...st, state: "error", error: "服务重启，任务中断，请重新提交", finished: Date.now() });
    }
  }
}

const safeName = (n, i) => {
  const ext = path.extname(n).toLowerCase().replace(/[^.a-z0-9]/g, "");
  const stem = path.basename(n, path.extname(n)).replace(/[\\/:*?"<>|\s]+/g, "_").slice(0, 60) || "file";
  return `${String(i).padStart(2, "0")}_${stem}${ext}`;
};

/**
 * 创建并排队一个评审任务。网页表单与 API 共用。
 * input: { stage, files:[{name, data:Buffer}], context:[{name,data}], content, context_text, transcript,
 *          runs, mode, model, effort, platform_hint, title, callback_url }
 */
export function createReview(input) {
  recover();
  const { stage } = input;
  if (!STAGES.includes(stage)) throw new ApiError(400, "invalid_stage", `stage 必须是 ${STAGES.join(" / ")} 之一`);
  const files = input.files || [];
  const ctxFiles = input.context || [];
  const content = (input.content || "").trim();
  const ctxText = (input.context_text || "").trim();
  const transcript = (input.transcript || "").trim();
  if (!files.length && !content) throw new ApiError(400, "missing_input", "请提供待评审文件（files）或文本（content）");
  for (const f of [...files, ...ctxFiles]) {
    if (!ALLOWED_EXT.test(f.name)) throw new ApiError(400, "unsupported_file", `不支持的文件类型：${f.name}`);
  }
  const total = [...files, ...ctxFiles].reduce((s, f) => s + f.data.length, 0);
  if (total > MAX_BYTES) throw new ApiError(413, "too_large", "文件合计超过 150MB，请压缩成片或抽取关键片段");
  if (stage === "video" && !files.some((f) => VIDEO_RE.test(f.name))) {
    throw new ApiError(400, "missing_video", "成片评审需要一个视频文件（mp4/mov/webm/m4v/mkv）");
  }
  if (stage !== "video" && files.some((f) => VIDEO_RE.test(f.name))) {
    throw new ApiError(400, "unexpected_video", "视频文件只能提交到 video 关卡");
  }
  const runs = input.runs == null || input.runs === "" ? 3 : Number(input.runs);
  if (![1, 2, 3].includes(runs)) throw new ApiError(400, "invalid_runs", "runs 必须是 1、2 或 3");
  const mode = input.mode || "sample";
  if (!["sample", "panel"].includes(mode)) throw new ApiError(400, "invalid_mode", "mode 必须是 sample 或 panel");
  // 评审模型由调用方指定（不传则用评审器默认的 REVIEW_MODEL）；配置了 REVIEW_ALLOWED_MODELS 时只接受清单里的
  const model = (input.model || "").trim() || null;
  if (model && !/^[A-Za-z0-9._:\/-]{1,80}$/.test(model)) throw new ApiError(400, "invalid_model", "model 只能包含字母、数字和 . _ : / -");
  const allowed = (reviewEnv("REVIEW_ALLOWED_MODELS") || "").split(",").map((x) => x.trim()).filter(Boolean);
  if (model && allowed.length && !allowed.includes(model)) throw new ApiError(400, "invalid_model", `model 必须是以下之一：${allowed.join(", ")}`);
  const effort = input.effort || "high";
  if (!["off", "low", "high", "max"].includes(effort)) throw new ApiError(400, "invalid_effort", "effort 必须是 off（不思考）/ low / high / max");
  const cb = (input.callback_url || "").trim();
  if (cb && !/^https?:\/\/[^\s]+$/i.test(cb)) throw new ApiError(400, "invalid_callback_url", "callback_url 必须是 http(s) 地址");

  const id = `${new Date().toISOString().slice(0, 10).replace(/-/g, "")}-${crypto.randomBytes(4).toString("hex")}`;
  const dir = path.join(JOBS, id);
  const inDir = path.join(dir, "inputs");
  fs.mkdirSync(inDir, { recursive: true });
  const save = (f, i, prefix) => {
    const p = path.join(inDir, prefix + safeName(f.name, i));
    fs.writeFileSync(p, f.data);
    return p;
  };
  const filePaths = files.map((f, i) => save(f, i + 1, ""));
  if (content) {
    const p = path.join(inDir, "00_content.md");
    fs.writeFileSync(p, content);
    filePaths.unshift(p);
  }
  const ctxPaths = ctxFiles.map((f, i) => save(f, i + 1, "ctx_"));
  if (ctxText) {
    const p = path.join(inDir, "ctx_00_context.md");
    fs.writeFileSync(p, ctxText);
    ctxPaths.unshift(p);
  }
  let transcriptPath = null;
  if (transcript) {
    transcriptPath = path.join(inDir, "transcript.txt");
    fs.writeFileSync(transcriptPath, transcript);
  } else {
    // 成片未单独提供台词时，上传的 .srt 作为字幕
    const srt = filePaths.find((p) => p.endsWith(".srt"));
    if (srt && stage === "video") {
      transcriptPath = srt;
      filePaths.splice(filePaths.indexOf(srt), 1);
    }
  }
  const job = {
    stage, files: filePaths, context: ctxPaths, transcript: transcriptPath, runs, mode, model, effort,
    platform_hint: (input.platform_hint || "").trim() || null,
    title: (input.title || "").trim().slice(0, 80) || files[0]?.name || "文本内容",
    callback_url: cb || null,
    source: input.source || "api",
  };
  write(dir, "job.json", job);
  write(dir, "status.json", { state: "queued", created: Date.now() });
  Q.queue.push(id);
  pump();
  return id;
}

async function notify(id) {
  const j = getJob(id);
  if (!j?.job?.callback_url) return;
  const body = JSON.stringify(serializeReview(j));
  for (let i = 0; i < 3; i++) {
    try {
      const r = await fetch(j.job.callback_url, { method: "POST", headers: { "Content-Type": "application/json" }, body, signal: AbortSignal.timeout(10000) });
      fs.appendFileSync(path.join(JOBS, id, "log.txt"), `\n[callback] ${j.job.callback_url} → HTTP ${r.status}\n`);
      if (r.ok) return;
    } catch (e) {
      fs.appendFileSync(path.join(JOBS, id, "log.txt"), `\n[callback] ${j.job.callback_url} 失败：${e.message}\n`);
    }
    await new Promise((res) => setTimeout(res, 2000 * 2 ** i));
  }
}

function pump() {
  while (Q.running.size < MAX_RUNNING && Q.queue.length) {
    const id = Q.queue.shift();
    const dir = path.join(JOBS, id);
    Q.running.add(id);
    const st = read(dir, "status.json") || {};
    write(dir, "status.json", { ...st, state: "running", started: Date.now() });
    const log = fs.openSync(path.join(dir, "log.txt"), "a");
    const p = spawn(PYTHON, [path.join(SITE, "worker", "run_job.py"), dir], { stdio: ["ignore", log, log] });
    p.on("exit", (code) => {
      fs.closeSync(log);
      Q.running.delete(id);
      const cur = read(dir, "status.json") || {};
      if (cur.state === "running") {
        const tail = (fs.readFileSync(path.join(dir, "log.txt"), "utf8").trim().split("\n").pop() || "").slice(0, 300);
        write(dir, "status.json", { ...cur, state: "error", error: `评审进程异常退出（${code}）：${tail}`, finished: Date.now() });
      }
      notify(id);
      pump();
    });
  }
}

export function getJob(id) {
  recover();
  const dir = jobDir(id);
  if (!dir) return null;
  const job = read(dir, "job.json");
  if (!job) return null;
  const status = read(dir, "status.json") || { state: "unknown" };
  const position = status.state === "queued" ? Q.queue.indexOf(id) + 1 : 0;
  const result = status.state === "done" ? read(dir, "result.json") : null;
  return { id, job, status: { ...status, position }, result };
}

export function listJobs({ limit = 50, offset = 0, stage, state } = {}) {
  recover();
  if (!fs.existsSync(JOBS)) return { total: 0, items: [] };
  const all = fs
    .readdirSync(JOBS)
    .map((id) => {
      const dir = path.join(JOBS, id);
      const job = read(dir, "job.json");
      const status = read(dir, "status.json");
      if (!job || !status) return null;
      const res = status.state === "done" ? read(dir, "result.json")?.result : null;
      return { id, job, status, verdict: res?.verdict, total: res?.total };
    })
    .filter((j) => j && (!stage || j.job.stage === stage) && (!state || j.status.state === state))
    .sort((a, b) => (b.status.created || 0) - (a.status.created || 0));
  return { total: all.length, items: all.slice(offset, offset + limit) };
}

export function deleteJob(id) {
  const dir = jobDir(id);
  if (!dir) return false;
  if (Q.running.has(id)) throw new ApiError(409, "job_running", "任务正在评审中，完成后才能删除");
  const qi = Q.queue.indexOf(id);
  if (qi >= 0) Q.queue.splice(qi, 1);
  fs.rmSync(dir, { recursive: true, force: true });
  return true;
}

export const queueState = () => ({ running: Q.running.size, queued: Q.queue.length, max_running: MAX_RUNNING });
