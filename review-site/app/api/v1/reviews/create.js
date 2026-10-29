import { ApiError, baseUrl, readReviewInput, serializeReview } from "@/lib/api";
import { createReview, getJob } from "@/lib/jobs";

// POST /api/v1/reviews 与 POST /api/v1/reviews/{stage} 共用
export async function create(req, stageFromPath) {
  const input = await readReviewInput(req);
  const stage = stageFromPath || new URL(req.url).searchParams.get("stage") || input.stage;
  const id = await createReview({ ...input, stage, source: req.headers.get("x-client") === "web" ? "web" : "api" });
  const wait = Math.min(Math.max(Number(input.wait || new URL(req.url).searchParams.get("wait") || 0), 0), 300);
  const deadline = Date.now() + wait * 1000;
  let j = getJob(id);
  while (wait && Date.now() < deadline && ["queued", "running"].includes(j.status.state)) {
    await new Promise((r) => setTimeout(r, 2000));
    j = getJob(id);
  }
  const body = serializeReview(j, baseUrl(req));
  const finished = ["done", "error"].includes(j.status.state);
  return Response.json(body, { status: finished ? 200 : 202, headers: { Location: body.links.self } });
}

export function assertStage(stage) {
  if (!["creative", "storyboard", "asset", "video"].includes(stage)) throw new ApiError(404, "not_found", "评审任务不存在");
}
