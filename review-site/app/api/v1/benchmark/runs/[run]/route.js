import { ApiError, handler } from "@/lib/api";
import { runInfo } from "@/lib/bench";

export const dynamic = "force-dynamic";

export const GET = handler(async (req, { params }) => {
  const r = runInfo((await params).run, { rows: new URL(req.url).searchParams.get("include") === "rows" });
  if (!r) throw new ApiError(404, "not_found", "评测轮次不存在");
  return Response.json(r);
});
