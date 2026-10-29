"""C 层测试专用：网站以 PYTHON=<venv python> 加 PYTHONPATH=<本目录> 启动工作进程时自动加载。

- C_STUB_URL：把 video_review.api_url() 指向测试进程里的模型桩，绝不调用付费接口
- 任务标题为 __crash__ 时直接以退出码 3 结束，模拟工作进程崩溃
- 被调用的是 run_benchmark.py 时睡 C_BENCH_SLEEP 秒后退出 0，只测网站的轮次管理，不跑真实基准
"""
import json
import os
import sys
import time
from pathlib import Path

_argv = getattr(sys, "orig_argv", sys.argv)
_script = next((a for a in _argv[1:] if a.endswith(".py")), "")

if os.path.basename(_script) == "run_benchmark.py":
    time.sleep(float(os.environ.get("C_BENCH_SLEEP", "3")))
    os._exit(0)

if os.path.basename(_script) == "run_job.py" and os.environ.get("C_STUB_URL"):
    sys.path.insert(0, os.environ["C_REAL_ROOT"])
    import video_review  # noqa: E402  先于 run_job 导入，run_job 拿到的是同一个已打桩模块

    video_review.api_url = lambda: os.environ["C_STUB_URL"]
    try:
        job_dir = Path(_argv[_argv.index(_script) + 1])
        if json.loads((job_dir / "job.json").read_text(encoding="utf-8")).get("title") == "__crash__":
            print("simulated crash", flush=True)
            os._exit(3)
    except (IndexError, OSError, ValueError):
        pass
