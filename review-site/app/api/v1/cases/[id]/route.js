import { ApiError, baseUrl, handler } from "@/lib/api";
import { getCase } from "@/lib/cases";

export const dynamic = "force-dynamic";

export const GET = handler(async (req, { params }) => {
  const sp = new URL(req.url).searchParams;
  const inc = (sp.get("include") || "").split(",");
  const c = getCase((await params).id, sp.get("run") || undefined, baseUrl(req), { raw: inc.includes("raw_runs"), text: !sp.has("no_text") });
  if (!c) throw new ApiError(404, "not_found", "用例不存在");
  return Response.json(c);
});
