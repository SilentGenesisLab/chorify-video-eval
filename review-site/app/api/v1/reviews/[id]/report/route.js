import fs from "node:fs";
import path from "node:path";
import { ApiError, handler } from "@/lib/api";
import { jobDir } from "@/lib/jobs";

export const dynamic = "force-dynamic";

export const GET = handler(async (req, { params }) => {
  const dir = jobDir((await params).id);
  if (!dir) throw new ApiError(404, "not_found", "评审任务不存在");
  const p = path.join(dir, "report.md");
  if (!fs.existsSync(p)) throw new ApiError(409, "not_ready", "评审尚未完成，报告还未生成");
  return new Response(fs.readFileSync(p, "utf8"), { headers: { "Content-Type": "text/markdown; charset=utf-8" } });
});
