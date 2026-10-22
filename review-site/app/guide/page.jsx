import path from "node:path";
import { SITE, doc, readText } from "@/lib/data";
import DocPage from "../doc-page";

export const dynamic = "force-dynamic";
export const metadata = { title: "使用指南 · 视频评审台" };

export default function Page() {
  const { html, toc } = doc(readText(path.join(SITE, "docs", "使用手册.md")));
  return <DocPage html={html} toc={toc} source="review-site/docs/使用手册.md" />;
}
