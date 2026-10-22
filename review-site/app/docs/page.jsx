import path from "node:path";
import { SITE, doc, readText } from "@/lib/data";
import DocPage from "../doc-page";

export const dynamic = "force-dynamic";
export const metadata = { title: "接口文档 · 视频评审台" };

export default function Page() {
  const base = (process.env.PUBLIC_BASE_URL || "http://localhost:3100").replace(/\/$/, "");
  const { html, toc } = doc(readText(path.join(SITE, "docs", "API文档.md")).replaceAll("{{BASE_URL}}", base));
  return <DocPage html={html} toc={toc} source="review-site/docs/API文档.md · OpenAPI：/api/v1/openapi.json" />;
}
