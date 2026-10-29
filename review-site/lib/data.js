import fs from "node:fs";
import path from "node:path";
import { Marked } from "marked";

// 站点读取的是评审器工程里的真实文件，评测结果更新后刷新页面即可看到
export const ROOT = path.resolve(process.env.REVIEW_ROOT || path.join(process.cwd(), ".."));
export const BENCH = path.join(ROOT, "benchmark");
export const SITE = process.cwd();
export const STAGES = ["creative", "storyboard", "asset", "video"];
export const STAGE_NAMES = { creative: "创意", storyboard: "分镜", asset: "资产", video: "成片" };
export const KIND_NAMES = { base: "基准", redline: "红线", quality: "质量缺陷", invariance: "不变性" };

const readJSON = (p, fallback = null) => {
  try {
    return JSON.parse(fs.readFileSync(p, "utf8"));
  } catch {
    return fallback;
  }
};

export const readText = (p) => {
  try {
    return fs.readFileSync(p, "utf8");
  } catch {
    return null;
  }
};

// 数据集与评审材料里的 Markdown：去掉原始 HTML，只保留 http(s) / mailto / 相对链接
const escapeHtml = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const safeHref = (href) => (/^(https?:|mailto:)/i.test(href || "") || !/^[a-z][a-z0-9+.-]*:/i.test(href || "") ? href : null);
const safeMarked = new Marked({
  gfm: true,
  renderer: {
    html() {
      return "";
    },
    link({ href, title, tokens }) {
      const label = this.parser.parseInline(tokens);
      const h = safeHref(href);
      return h == null ? label : `<a href="${escapeHtml(h)}"${title ? ` title="${escapeHtml(title)}"` : ""}>${label}</a>`;
    },
    image({ href, title, text }) {
      const h = safeHref(href);
      return h == null ? escapeHtml(text) : `<img src="${escapeHtml(h)}" alt="${escapeHtml(text)}"${title ? ` title="${escapeHtml(title)}"` : ""}>`;
    },
  },
});

export const md = (text) => safeMarked.parse(text || "");

// 带目录的长文档：给 h2/h3 加锚点
export function doc(text) {
  const toc = [];
  const seen = {};
  const m = new Marked({
    gfm: true,
    renderer: {
      heading({ tokens, depth, text: raw }) {
        const base = raw.replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-|-$/g, "").toLowerCase() || "s";
        seen[base] = (seen[base] || 0) + 1;
        const id = seen[base] > 1 ? `${base}-${seen[base]}` : base;
        if (depth === 2 || depth === 3) toc.push({ id, depth, text: raw.replace(/[*`]/g, "") });
        return `<h${depth} id="${id}">${this.parser.parseInline(tokens)}</h${depth}>`;
      },
    },
  });
  return { html: m.parse(text || ""), toc };
}

export function rubric() {
  return readJSON(path.join(ROOT, "rubrics.json"));
}

export function labels() {
  const t = readText(path.join(BENCH, "dataset", "labels.jsonl")) || "";
  return t.split("\n").filter(Boolean).map((x) => JSON.parse(x));
}

export function label(id) {
  return labels().find((l) => l.case_id === id) || null;
}

// 有 summary.json 的评测轮次，测试集优先、新的在前
export function runs() {
  const dir = path.join(BENCH, "results");
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((n) => fs.existsSync(path.join(dir, n, "summary.json")))
    .map((n) => {
      const s = readJSON(path.join(dir, n, "summary.json"));
      const mtime = fs.statSync(path.join(dir, n, "summary.json")).mtimeMs;
      return { name: n, cases: s.cases, passed: s.passed, split: n.startsWith("test") ? "test" : "dev", mtime };
    })
    .sort((a, b) => (a.split === b.split ? b.mtime - a.mtime : a.split === "test" ? -1 : 1));
}

export function summary(run) {
  return readJSON(path.join(BENCH, "results", run, "summary.json"));
}

export function caseResult(run, id) {
  return readJSON(path.join(BENCH, "results", run, `${id}.json`));
}

// 用例所在轮次：优先指定轮次，否则在所有轮次里找
export function findResult(id, preferred) {
  const names = [preferred, ...runs().map((r) => r.name)].filter(Boolean);
  for (const n of names) {
    const r = caseResult(n, id);
    if (r) return { run: n, ...r };
  }
  return null;
}

export function caseRow(run, id) {
  return summary(run)?.rows?.find((r) => r.case_id === id) || null;
}

export function mediaUrl(rel) {
  return "/media/" + rel.split("/").map(encodeURIComponent).join("/");
}

export function fileKind(p) {
  const ext = path.extname(p).toLowerCase();
  if ([".png", ".jpg", ".jpeg", ".webp", ".gif"].includes(ext)) return "image";
  if ([".mp4", ".mov", ".webm", ".m4v", ".mkv"].includes(ext)) return "video";
  if ([".mp3", ".wav", ".m4a", ".aac"].includes(ext)) return "audio";
  return "text";
}

/** 评审器配置（与 video_review.py 同一来源：环境变量优先，其次仓库根目录 .env）。 */
export function reviewEnv(name) {
  if (process.env[name]) return process.env[name];
  try {
    return new RegExp(`^${name}=(.+)$`, "m").exec(fs.readFileSync(path.join(ROOT, ".env"), "utf8"))?.[1]?.trim() || null;
  } catch {
    return null;
  }
}

export const reviewModel = () => reviewEnv("REVIEW_MODEL") || "deepseek-flash";
