import fs from "node:fs";
import path from "node:path";
import { ROOT, reviewEnv, reviewModel } from "@/lib/data";
import { handler } from "@/lib/api";
import { queueState } from "@/lib/jobs";

export const dynamic = "force-dynamic";

async function balance() {
  // 换用其他接口时没有 DeepSeek 余额可查
  if (reviewEnv("REVIEW_API_URL") && !/api\.deepseek\.com/.test(reviewEnv("REVIEW_API_URL"))) return { available: null, note: "当前评审接口不是 DeepSeek，不查询余额" };
  try {
    const key = process.env.DEEPSEEK_API_KEY || /DEEPSEEK_API_KEY=(.+)/.exec(fs.readFileSync(path.join(ROOT, ".env"), "utf8"))?.[1]?.trim();
    const r = await fetch("https://api.deepseek.com/user/balance", { headers: { Authorization: `Bearer ${key}` }, signal: AbortSignal.timeout(5000) });
    const d = await r.json();
    const b = d.balance_infos?.[0];
    return { available: d.is_available, currency: b?.currency, total: b ? Number(b.total_balance) : null };
  } catch (e) {
    return { available: null, error: e.message };
  }
}

export const GET = handler(async () => {
  return Response.json({ status: "ok", version: "v1", model: reviewModel(), queue: queueState(), deepseek_balance: await balance(), time: new Date().toISOString() });
});
