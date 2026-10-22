import { rubric } from "@/lib/data";
import { handler } from "@/lib/api";

export const dynamic = "force-dynamic";

export const GET = handler(async () => {
  const rb = rubric();
  return Response.json({ scale: rb.scale, verdict_rules: rb.verdict_rules, stages: rb.stages });
});
