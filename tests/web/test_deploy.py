"""C9 部署配置静态检查、C10 依赖漏洞。不需要启动网站。"""
import json
import re
import shutil
import subprocess

import pytest

import harness as h

DEPLOY = h.ROOT / "deploy"
NGINX = (DEPLOY / "nginx-review.conf").read_text(encoding="utf-8")
SERVICE = (DEPLOY / "video-review.service").read_text(encoding="utf-8")


def _mb(v):
    n, unit = re.fullmatch(r"(\d+)([kmg]?)", v.lower()).groups()
    return int(n) * {"": 1 / 2 ** 20, "k": 1 / 1024, "m": 1, "g": 1024}[unit]


def test_service_binds_loopback():
    assert re.search(r"next start .*-H 127\.0\.0\.1", SERVICE)
    assert "EnvironmentFile=" in SERVICE and "NODE_ENV=production" in SERVICE


def test_nginx_proxies_to_service_port():
    port = re.search(r"-p (\d+)", SERVICE)[1]
    assert f"proxy_pass http://127.0.0.1:{port}" in NGINX


def test_nginx_timeout_covers_wait():
    # 同步等待最长 300 秒
    assert int(re.search(r"proxy_read_timeout (\d+)s", NGINX)[1]) > 300


def test_nginx_body_limit_covers_multipart():
    assert _mb(re.search(r"client_max_body_size (\w+);", NGINX)[1]) >= 150


def test_nginx_body_limit_covers_base64_json():
    # 150MB 文件 base64 后 ×4/3 ≈ 200MB，再加 JSON 外壳
    assert _mb(re.search(r"client_max_body_size (\w+);", NGINX)[1]) >= 210


def test_nginx_strips_middleware_subrequest_header():
    assert re.search(r'proxy_set_header\s+x-middleware-subrequest\s+""', NGINX, re.I)


def test_serve_sh_binds_loopback():
    sh = (h.SITE_SRC / "serve.sh").read_text(encoding="utf-8")
    assert "-H 0.0.0.0" not in sh


def test_nginx_https_only():
    """Basic Auth 密码和 API Token 每个请求都明文带着，仓库里的配置本身就应该强制 HTTPS。"""
    assert re.search(r"listen\s+(\[::\]:)?443\s+ssl", NGINX), "没有监听 443"
    assert re.search(r"return\s+30[18]\s+https://", NGINX), "80 端口没有跳转 HTTPS"
    assert re.search(r'add_header\s+Strict-Transport-Security\s+"max-age=\d+', NGINX, re.I), "没有 HSTS"


def test_secrets_not_tracked():
    out = subprocess.run(["git", "ls-files"], cwd=h.ROOT, capture_output=True, text=True, encoding="utf-8").stdout.split()
    assert not [f for f in out if re.search(r"(^|/)\.env(\.local)?$", f)], "密钥文件进了 git"
    gi = (h.ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "review-site/.env.local" in gi and "review-site/data/" in gi


def _ver(v):
    return tuple(int(x) for x in re.match(r"(\d+)\.(\d+)\.(\d+)", v).groups())


# CVE-2025-55182/66478（RSC RCE）的补丁按小版本线发布：同一条线要 ≥ 补丁版本；
# 比表里最新一条线还新的小版本发布时已含补丁；比最早一条线还旧的（next < 15.0、react < 19.0）不带 RSC，不受影响
PATCHED = {
    "next": {(15, 0): (15, 0, 5), (15, 1): (15, 1, 9), (15, 2): (15, 2, 6), (15, 3): (15, 3, 6),
             (15, 4): (15, 4, 8), (15, 5): (15, 5, 7), (16, 0): (16, 0, 7)},
    "react": {(19, 0): (19, 0, 1), (19, 1): (19, 1, 2), (19, 2): (19, 2, 1)},
}
PATCHED["react-dom"] = PATCHED["react"]


def rsc_patched(pkg, version):
    v, lines = _ver(version), PATCHED[pkg]
    if v[:2] in lines:
        return v >= lines[v[:2]]
    return v[:2] > max(lines) or v[:2] < min(lines)


@pytest.mark.parametrize("pkg,version,ok", [
    ("react", "19.0.0", False), ("react", "19.0.1", True), ("react", "19.0.9", True),
    ("react", "19.1.0", False), ("react", "19.1.1", False), ("react", "19.1.2", True),
    ("react", "19.2.0", False), ("react", "19.2.1", True), ("react", "19.3.0", True),
    ("next", "15.1.6", False), ("next", "15.1.9", True), ("next", "15.5.6", False), ("next", "15.5.28", True),
    ("next", "16.0.6", False), ("next", "16.0.7", True), ("next", "16.1.0", True), ("next", "14.2.30", True),
])
def test_rsc_patch_judge(pkg, version, ok):
    """判据自检：补丁是分小版本线的，不能只比一个下限。"""
    assert rsc_patched(pkg, version) is ok


def test_dependency_versions_patched():
    v = h.versions()
    assert _ver(v["next"]) >= (15, 2, 3), f"next {v['next']} 受 CVE-2025-29927 影响"
    for p in ("next", "react", "react-dom"):
        assert rsc_patched(p, v[p]), f"{p} {v[p]} 受 CVE-2025-55182/66478 影响"


def test_lockfile_matches_package_json():
    pkg = json.loads((h.SITE_SRC / "package.json").read_text(encoding="utf-8"))["dependencies"]
    lock = json.loads((h.SITE_SRC / "package-lock.json").read_text(encoding="utf-8"))["packages"]
    for name, want in pkg.items():
        assert lock[f"node_modules/{name}"]["version"] == want, name
    assert all(re.fullmatch(r"\d+\.\d+\.\d+", v) for v in pkg.values()), "依赖应锁定精确版本"


@pytest.mark.skipif(not shutil.which("npm"), reason="没有 npm")
def test_npm_audit_no_high_or_critical():
    """查询 npm 官方漏洞库（只发送依赖名与版本）。网络不通时跳过，而不是假通过。"""
    p = subprocess.run("npm audit --json --omit=dev", cwd=h.SITE_SRC, capture_output=True, text=True,
                       encoding="utf-8", shell=True, timeout=120)
    try:
        meta = json.loads(p.stdout)["metadata"]["vulnerabilities"]
    except (ValueError, KeyError):
        pytest.skip(f"npm audit 无结果：{p.stderr[-300:]}")
    assert meta["high"] == 0 and meta["critical"] == 0, meta
