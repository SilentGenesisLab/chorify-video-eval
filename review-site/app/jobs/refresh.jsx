"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

// 任务未完成时每 4 秒刷新一次服务端数据
export default function AutoRefresh({ active }) {
  const router = useRouter();
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => router.refresh(), 4000);
    return () => clearInterval(t);
  }, [active, router]);
  return null;
}
