import { ApiError, handler } from "@/lib/api";
import { listRuns, startRun } from "@/lib/bench";

export const dynamic = "force-dynamic";

export const GET = handler(async () => Response.json({ items: listRuns() }));

export const POST = handler(async (req) => {
  let body;
  try {
    body = await req.json();
  } catch {
    throw new ApiError(400, "invalid_body", "请求体需为 JSON");
  }
  const r = startRun(body);
  return Response.json(r, { status: r.dry_run ? 200 : 202 });
});
