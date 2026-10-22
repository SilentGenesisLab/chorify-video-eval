import { rubric } from "@/lib/data";
import { ApiError, handler } from "@/lib/api";

export const dynamic = "force-dynamic";

export const GET = handler(async (req, { params }) => {
  const { stage } = await params;
  const rb = rubric();
  const s = rb.stages[stage];
  if (!s) throw new ApiError(404, "not_found", `关卡 ${stage} 不存在，可选：${Object.keys(rb.stages).join(" / ")}`);
  return Response.json({ stage, verdict_rules: rb.verdict_rules, ...s, redlines: s.redlines.map((t, i) => ({ id: `R${i + 1}`, text: t })) });
});
