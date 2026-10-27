import path from "node:path";
import { BENCH, readText, reviewModel, rubric } from "@/lib/data";
import EvaluateForm from "./form";

export const dynamic = "force-dynamic";
export const metadata = { title: "在线评审 · 视频评审台" };

export default function Page() {
  const ctx = (f) => readText(path.join(BENCH, "dataset", "cases", "S03_context", f)) || "";
  // 示例取自测试集 S03（在线英语 App），只用于演示填写方式
  const samples = {
    creative: { main: ctx("creative.md"), context: "" },
    storyboard: { main: readText(path.join(BENCH, "dataset", "cases", "S03_storyboard_base", "storyboard.md")) || "", context: ctx("creative.md") },
    asset: { main: "", context: ctx("storyboard.md") + "\n\n" + ctx("brand_guide.md") },
    video: { main: "", context: ctx("storyboard.md") },
  };
  const stages = Object.fromEntries(Object.entries(rubric().stages).map(([k, s]) => [k, { name: s.name, redlines: s.redlines.length, dims: s.dimensions.length }]));
  return (
    <main className="wrap narrow">
      <div className="head">
        <span className="eyebrow">{reviewModel()} · 结果约 1–3 分钟</span>
        <h1>在线评审</h1>
        <p className="lede">选择关卡，上传或粘贴待评审材料，附上前序关卡的参考材料（brief、创意、分镜、品牌规范），评审器会对照还原度打分。默认每份材料独立评 3 次取均值，分歧大的项会提示人工复核。</p>
      </div>
      <EvaluateForm samples={samples} stages={stages} />
    </main>
  );
}
