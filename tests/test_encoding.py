"""B01：文件读写必须显式指定编码。

静态检查在任何平台都确定；运行时用例在本机默认编码不是 UTF-8 时（如 Windows 中文版 cp936）复现真实故障。
"""
import ast
import locale
import os
import subprocess
import sys

import pytest

from bugs import bug
from conftest import ROOT, SRC

FILES = [SRC / "video_review.py", ROOT / "review-site" / "worker" / "run_job.py",
         ROOT / "benchmark" / "run_benchmark.py", ROOT / "benchmark" / "human_agreement.py"]


def unencoded_calls(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
        kw = {k.arg for k in node.keywords}
        if name in ("read_text", "write_text") and "encoding" not in kw:
            bad.append(f"{path.name}:{node.lineno} {name}")
        is_pil = isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "Image"  # PIL 打开图片，不是文本
        if name == "open" and "encoding" not in kw and not is_pil:
            mode = node.args[1].value if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) else ""
            if "b" not in str(mode):
                bad.append(f"{path.name}:{node.lineno} open")
    return bad


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_all_text_io_specifies_encoding(path):
    assert unencoded_calls(path) == []


def test_static_checker_itself(tmp_path):
    # 防止检查器本身失效导致 B01 用例"假通过"
    p = tmp_path / "s.py"
    p.write_text("a.read_text()\nb.write_text(x, encoding='utf-8')\nopen(f)\nopen(f, 'rb')\nopen(f, 'w', encoding='utf-8')\n",
                 encoding="utf-8")
    assert unencoded_calls(p) == ["s.py:1 read_text", "s.py:3 open"]


@pytest.mark.skipif(sys.platform != "win32", reason="只在 Windows 非 UTF-8 区域设置下复现")
def test_rubric_loads_under_system_locale(tmp_path):
    env = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "utf-8"}
    code = f"import sys,json; sys.path.insert(0, r'{SRC}'); import video_review as v; from pathlib import Path; " \
           f"v.load_rubric(); v.read_text_file(v.HERE / 'rubrics.json'); v.env_value('NO_SUCH_KEY')"
    enc = subprocess.run([sys.executable, "-X", "utf8=0", "-c", "import locale;print(locale.getpreferredencoding(False))"],
                         capture_output=True, text=True, env=env).stdout.strip()
    if enc.lower().replace("-", "") == "utf8":
        pytest.skip("本机默认编码已是 UTF-8")
    p = subprocess.run([sys.executable, "-X", "utf8=0", "-c", code], capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr[-300:]
