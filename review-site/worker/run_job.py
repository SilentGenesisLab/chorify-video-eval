#!/usr/bin/env python3
"""网站在线评审的工作进程：读取任务目录里的 job.json，调用 video_review.evaluate，写回结果。

python run_job.py <job_dir>
"""
import json
import sys
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import video_review  # noqa: E402


def main():
    d = Path(sys.argv[1])
    job = json.loads((d / "job.json").read_text(encoding="utf-8"))
    status = json.loads((d / "status.json").read_text(encoding="utf-8"))
    try:
        ev = video_review.evaluate(job["stage"], job["files"], job.get("context") or None, job.get("transcript"),
                                   runs=job.get("runs", 3), effort=job.get("effort", "high"), mode=job.get("mode", "sample"), model=job.get("model") or None,
                                   platform_hint=job.get("platform_hint") or video_review.DEFAULT_PLATFORM_HINT)
        (d / "result.json").write_text(json.dumps(ev, ensure_ascii=False, indent=1), encoding="utf-8")
        args = SimpleNamespace(files=job["files"], model=ev["model"], runs=job.get("runs", 3))
        (d / "report.md").write_text(video_review.render_markdown(ev["result"], ev["tech"], args, ev["usage"]), encoding="utf-8")
        status.update(state="done", finished=time.time() * 1000)
    except Exception as e:
        traceback.print_exc()
        status.update(state="error", error=str(e)[:500], finished=time.time() * 1000)
    (d / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
