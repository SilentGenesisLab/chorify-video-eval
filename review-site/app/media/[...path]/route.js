import fs from "node:fs";
import path from "node:path";
import { Readable } from "node:stream";
import { BENCH, SITE } from "@/lib/data";

// 只允许读取数据集与在线评审任务目录，支持 Range 以便视频拖动进度
const ALLOWED = [path.join(BENCH, "dataset"), path.join(SITE, "data", "jobs")];
const TYPES = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
  ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm", ".m4v": "video/mp4",
  ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".md": "text/markdown; charset=utf-8",
  ".srt": "text/plain; charset=utf-8", ".txt": "text/plain; charset=utf-8", ".json": "application/json" };

export const dynamic = "force-dynamic";

const notFound = () => new Response("not found", { status: 404 });

// 任务目录里只开放上传的材料和报告；job.json / status.json / log.txt 含服务器路径、回调地址和堆栈
const jobFileVisible = (rest) => (rest.length === 3 && rest[1] === "inputs") || (rest.length === 2 && rest[1] === "report.md");

/** 解析单个 bytes 范围（RFC 9110 §14.1.2）。返回 {start,end}、"unsatisfiable"，或 null 表示忽略 Range 头返回整个文件。 */
function parseRange(header, size) {
  const m = /^bytes=(\d*)-(\d*)$/.exec(header.trim());
  if (!m || (!m[1] && !m[2])) return null; // 不认识的单位、多段范围、无效语法：忽略
  if (!m[1]) {
    const n = Number(m[2]);
    if (n === 0) return "unsatisfiable";
    return { start: Math.max(size - n, 0), end: size - 1 }; // 后缀长度超过文件长度时取整个文件
  }
  const start = Number(m[1]);
  const end = m[2] ? Math.min(Number(m[2]), size - 1) : size - 1; // 结束位置超出文件长度时截断到末尾
  if (m[2] && Number(m[2]) < start) return "unsatisfiable";
  if (start >= size) return "unsatisfiable";
  return { start, end };
}

export async function GET(req, { params }) {
  // 路由层已经把每一段解码过一次，这里不再解码：%252E 只能对应字面量 %2E
  const parts = (await params).path;
  if (parts.some((p) => !p || p === "." || p === ".." || /[\\/\0]/.test(p) || /^[a-z]:/i.test(p))) return notFound();
  const roots = { dataset: ALLOWED[0], jobs: ALLOWED[1] };
  const [head, ...rest] = parts;
  const base = roots[head];
  if (!base || !rest.length) return notFound();
  if (head === "jobs" && !jobFileVisible(rest)) return notFound();
  const file = path.resolve(base, ...rest);
  if (!file.startsWith(base + path.sep)) return notFound();
  let st;
  try {
    st = fs.statSync(file);
  } catch {
    return notFound();
  }
  if (!st.isFile()) return notFound();
  const size = st.size;
  const type = TYPES[path.extname(file).toLowerCase()] || "application/octet-stream";
  const headers = { "Content-Type": type, "Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600" };
  const range = req.headers.get("range");
  const r = range ? parseRange(range, size) : null;
  if (r === "unsatisfiable") return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${size}` } });
  if (r) {
    const stream = Readable.toWeb(fs.createReadStream(file, { start: r.start, end: r.end }));
    return new Response(stream, { status: 206, headers: { ...headers, "Content-Range": `bytes ${r.start}-${r.end}/${size}`, "Content-Length": String(r.end - r.start + 1) } });
  }
  return new Response(Readable.toWeb(fs.createReadStream(file)), { headers: { ...headers, "Content-Length": String(size) } });
}
