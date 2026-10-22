import { handler, page } from "@/lib/api";
import { queryCases } from "@/lib/cases";

export const dynamic = "force-dynamic";

export const GET = handler(async (req) => {
  const sp = new URL(req.url).searchParams;
  const { limit, offset } = page(sp, 50, 500);
  const { items, total } = queryCases(sp);
  return Response.json({ total, limit, offset, items: items.slice(offset, offset + limit) });
});
