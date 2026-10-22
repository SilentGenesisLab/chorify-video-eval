import { baseUrl, handler } from "@/lib/api";
import { openapi } from "@/lib/openapi";

export const dynamic = "force-dynamic";

export const GET = handler(async (req) => Response.json(openapi(baseUrl(req))));
