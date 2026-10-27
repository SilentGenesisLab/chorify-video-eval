import path from "node:path";

// /api/v1 公共工具：统一错误格式、分页、输入解析、结果序列化

export class ApiError extends Error {
  constructor(status, code, message, extra) {
    super(message);
    this.status = status;
    this.code = code;
    this.extra = extra;
  }
}

export function handler(fn) {
  return async (req, ctx) => {
    try {
      return await fn(req, ctx);
    } catch (e) {
      if (e instanceof ApiError) return Response.json({ error: { code: e.code, message: e.message, ...(e.extra || {}) } }, { status: e.status });
      console.error(e);
      return Response.json({ error: { code: "internal_error", message: "服务内部错误" } }, { status: 500 });
    }
  };
}

export const baseUrl = (req) => {
  if (process.env.PUBLIC_BASE_URL) return process.env.PUBLIC_BASE_URL.replace(/\/$/, "");
  const h = req?.headers;
  const host = h?.get("x-forwarded-host") || h?.get("host") || "localhost:3100";
  return `${h?.get("x-forwarded-proto") || "http"}://${host}`;
};

export const fileUrl = (base, rel) => `${base}/media/${rel.split("/").map(encodeURIComponent).join("/")}`;

export function page(sp, def = 20, max = 200) {
  const limit = Math.min(Math.max(parseInt(sp.get("limit") || def, 10) || def, 1), max);
  const offset = Math.max(parseInt(sp.get("offset") || 0, 10) || 0, 0);
  return { limit, offset };
}

const MAX_URL_BYTES = 150 * 1024 * 1024;

async function fetchFile(f, i) {
  if (!/^https?:\/\//i.test(f.url)) throw new ApiError(400, "invalid_file_url", `files[${i}].url 必须是 http(s) 地址`);
  let r;
  try {
    r = await fetch(f.url, { signal: AbortSignal.timeout(120000) });
  } catch (e) {
    throw new ApiError(400, "file_download_failed", `下载 ${f.url} 失败：${e.message}`);
  }
  if (!r.ok) throw new ApiError(400, "file_download_failed", `下载 ${f.url} 失败：HTTP ${r.status}`);
  if (Number(r.headers.get("content-length") || 0) > MAX_URL_BYTES) throw new ApiError(413, "too_large", `${f.url} 超过 150MB`);
  const data = Buffer.from(await r.arrayBuffer());
  const name = f.name || decodeURIComponent(path.basename(new URL(f.url).pathname)) || `file_${i}`;
  return { name, data };
}

async function jsonFiles(list, field) {
  if (list == null) return [];
  if (!Array.isArray(list)) throw new ApiError(400, "invalid_body", `${field} 必须是数组`);
  const out = [];
  for (const [i, f] of list.entries()) {
    if (f?.content_base64) {
      if (!f.name) throw new ApiError(400, "invalid_body", `${field}[${i}] 缺少 name（需带扩展名，如 kv.png）`);
      out.push({ name: f.name, data: Buffer.from(f.content_base64, "base64") });
    } else if (f?.text != null) {
      out.push({ name: f.name || `${field}_${i + 1}.md`, data: Buffer.from(String(f.text)) });
    } else if (f?.url) {
      out.push(await fetchFile(f, i));
    } else {
      throw new ApiError(400, "invalid_body", `${field}[${i}] 需要 content_base64、text 或 url 之一`);
    }
  }
  return out;
}

const joinText = (v) => (Array.isArray(v) ? v.join("\n\n") : v || "");

// 评审提交：支持 multipart/form-data 与 application/json
export async function readReviewInput(req) {
  const type = req.headers.get("content-type") || "";
  if (type.includes("multipart/form-data")) {
    let form;
    try {
      form = await req.formData();
    } catch {
      throw new ApiError(400, "invalid_body", "multipart 内容无法解析（单次合计不超过 150MB）");
    }
    const files = async (k) => {
      const out = [];
      for (const f of form.getAll(k)) if (typeof f === "object" && f.size > 0) out.push({ name: f.name, data: Buffer.from(await f.arrayBuffer()) });
      return out;
    };
    const s = (k) => (form.get(k) ?? "").toString();
    return {
      stage: s("stage"), files: await files("files"), context: await files("context"), content: s("content"), context_text: s("context_text"),
      transcript: s("transcript"), runs: s("runs"), mode: s("mode") || undefined, model: s("model") || undefined, effort: s("effort") || undefined, platform_hint: s("platform_hint"),
      title: s("title"), callback_url: s("callback_url"), wait: s("wait"),
    };
  }
  if (type.includes("application/json")) {
    let b;
    try {
      b = await req.json();
    } catch {
      throw new ApiError(400, "invalid_body", "JSON 格式错误");
    }
    return {
      stage: b.stage, files: await jsonFiles(b.files, "files"), context: await jsonFiles(b.context_files, "context_files"),
      content: joinText(b.content), context_text: joinText(b.context), transcript: joinText(b.transcript),
      runs: b.runs, mode: b.mode, model: b.model, effort: b.effort, platform_hint: b.platform_hint, title: b.title, callback_url: b.callback_url, wait: b.wait,
    };
  }
  throw new ApiError(415, "unsupported_media_type", "Content-Type 需为 application/json 或 multipart/form-data");
}

const iso = (ms) => (ms ? new Date(ms).toISOString() : null);

export function serializeResult(ev, { raw = false } = {}) {
  if (!ev) return null;
  const r = ev.result;
  return {
    verdict: r.verdict, total: r.total, min_dimension: r.min_dimension, needs_human_review: r.needs_human_review,
    summary: r.summary, top_fixes: r.top_fixes, highlights: r.highlights, panels: r.panels || null,
    redlines: r.redlines.map((x) => ({ id: x.id, text: x.text, status: x.status, hits: x.hits, evidence: x.evidence })),
    dimensions: r.dimensions.map((d) => ({ id: d.id, name: d.name, weight: d.weight, score: d.mean, scores: d.scores, spread: d.spread, evidence: d.evidence, issues: d.issues, suggestions: d.suggestions })),
    tech: ev.tech || null, usage: ev.usage || null, model: ev.model || null, mode: ev.mode || "sample",
    ...(raw ? { raw_runs: ev.raw_runs } : {}),
  };
}

export function serializeReview(j, base = baseUrl(), opts = {}) {
  const st = j.status;
  const rel = (p) => `jobs/${j.id}/inputs/${path.basename(p)}`;
  const f = (p) => ({ name: path.basename(p), url: fileUrl(base, rel(p)) });
  return {
    id: j.id, stage: j.job.stage, title: j.job.title, status: st.state, error: st.error || null,
    queue_position: st.state === "queued" ? st.position : null,
    created_at: iso(st.created), started_at: iso(st.started), finished_at: iso(st.finished),
    elapsed_seconds: st.started ? Math.round(((st.finished || Date.now()) - st.started) / 1000) : null,
    params: { runs: j.job.runs, mode: j.job.mode || "sample", model: j.job.model || null, effort: j.job.effort, platform_hint: j.job.platform_hint, callback_url: j.job.callback_url },
    inputs: { files: j.job.files.map(f), context: j.job.context.map(f), transcript: j.job.transcript ? f(j.job.transcript) : null },
    result: serializeResult(j.result, opts),
    links: {
      self: `${base}/api/v1/reviews/${j.id}`,
      report: st.state === "done" ? `${base}/api/v1/reviews/${j.id}/report` : null,
      web: `${base}/jobs/${j.id}`,
    },
  };
}
