import { ApiError, handler } from "@/lib/api";
import { listRuns, startRun } from "@/lib/bench";

export const dynamic = "force-dynamic";

export const GET = handler(async () => Response.json({ items: listRuns() }));

export const POST = handler(async (req) => {
  // text/plain、表单是浏览器跨站「简单请求」，不触发预检：只接受 application/json
  if (!(req.headers.get("content-type") || "").toLowerCase().includes("application/json")) {
    throw new ApiError(415, "unsupported_media_type", "Content-Type 需为 application/json");
  }
  let body;
  try {
    body = await req.json();
  } catch {
    throw new ApiError(400, "invalid_body", "请求体需为 JSON");
  }
  const r = startRun(body);
  return Response.json(r, { status: r.dry_run ? 200 : 202 });
});
