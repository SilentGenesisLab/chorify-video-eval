import path from "node:path";
import { ROOT, doc, readText } from "@/lib/data";
import DocPage from "../doc-page";

export const dynamic = "force-dynamic";
export const metadata = { title: "评审框架 · 视频评审台" };

export default function Page() {
  const { html, toc } = doc(readText(path.join(ROOT, "视频评审框架.md")));
  return <DocPage html={html} toc={toc} source="视频评审框架.md" />;
}
