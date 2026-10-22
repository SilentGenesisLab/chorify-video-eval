"use client";
import { usePathname } from "next/navigation";

const LINKS = [
  ["/", "概览"],
  ["/framework", "评审框架"],
  ["/rubric", "评分标准"],
  ["/evaluate", "在线评审"],
  ["/jobs", "评审记录"],
  ["/benchmark", "基准测试"],
  ["/cases", "用例库"],
  ["/docs", "接口文档"],
  ["/guide", "使用指南"],
];

export default function Nav() {
  const p = usePathname();
  const on = (h) => (h === "/" ? p === "/" : p.startsWith(h));
  return (
    <nav className="nav" aria-label="主导航">
      {LINKS.map(([h, t]) => <a key={h} href={h} className={on(h) ? "on" : ""}>{t}</a>)}
    </nav>
  );
}
