import { ApiError, baseUrl, handler, serializeReview } from "@/lib/api";
import { getJob, deleteJob } from "@/lib/jobs";
import { create, assertStage } from "../create";

export const dynamic = "force-dynamic";

export const GET = handler(async (req, { params }) => {
  const { id } = await params;
  const j = getJob(id);
  if (!j) throw new ApiError(404, "not_found", "评审任务不存在");
  const raw = new URL(req.url).searchParams.get("include") === "raw_runs";
  return Response.json(serializeReview(j, baseUrl(req), { raw }));
});

// POST /api/v1/reviews/{stage}：提交评审
export const POST = handler(async (req, { params }) => {
  const { id: stage } = await params;
  assertStage(stage);
  return create(req, stage);
});

export const DELETE = handler(async (req, { params }) => {
  const { id } = await params;
  if (!deleteJob(id)) throw new ApiError(404, "not_found", "评审任务不存在");
  return new Response(null, { status: 204 });
});
