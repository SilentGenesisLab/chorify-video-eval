import { ApiError, baseUrl, handler, page, serializeReview } from "@/lib/api";
import { listJobs, getJob } from "@/lib/jobs";
import { create } from "./create";

export const dynamic = "force-dynamic";

export const GET = handler(async (req) => {
  const sp = new URL(req.url).searchParams;
  const { limit, offset } = page(sp);
  const state = sp.get("status") || undefined;
  if (state && !["queued", "running", "done", "error"].includes(state)) throw new ApiError(400, "invalid_status", "status 取 queued / running / done / error");
  const { total, items } = listJobs({ limit, offset, stage: sp.get("stage") || undefined, state });
  const base = baseUrl(req);
  return Response.json({
    total, limit, offset,
    items: items.map((j) => {
      const { result, inputs, ...rest } = serializeReview(getJob(j.id), base);
      return { ...rest, verdict: result?.verdict ?? null, total: result?.total ?? null };
    }),
  });
});

export const POST = handler((req) => create(req));
