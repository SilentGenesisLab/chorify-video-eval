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

export async function GET(req, { params }) {
  const parts = (await params).path;
  const rel = parts.map(decodeURIComponent).join("/");
  const roots = { dataset: ALLOWED[0], jobs: ALLOWED[1] };
  const [head, ...rest] = rel.split("/");
  const base = roots[head];
  if (!base) return new Response("not found", { status: 404 });
  const file = path.resolve(base, rest.join("/"));
  if (!file.startsWith(base + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    return new Response("not found", { status: 404 });
  }
  const size = fs.statSync(file).size;
  const type = TYPES[path.extname(file).toLowerCase()] || "application/octet-stream";
  const range = req.headers.get("range");
  const headers = { "Content-Type": type, "Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600" };
  if (range) {
    const m = /bytes=(\d*)-(\d*)/.exec(range);
    let start = m && m[1] ? Number(m[1]) : 0;
    let end = m && m[2] ? Number(m[2]) : size - 1;
    if (m && !m[1] && m[2]) { start = size - Number(m[2]); end = size - 1; }
    if (start >= size || end >= size || start > end) {
      return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${size}` } });
    }
    const stream = Readable.toWeb(fs.createReadStream(file, { start, end }));
    return new Response(stream, { status: 206, headers: { ...headers, "Content-Range": `bytes ${start}-${end}/${size}`, "Content-Length": String(end - start + 1) } });
  }
  return new Response(Readable.toWeb(fs.createReadStream(file)), { headers: { ...headers, "Content-Length": String(size) } });
}
