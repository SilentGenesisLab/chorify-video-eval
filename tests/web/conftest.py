"""C 层（网站 / 接口 / 安全）夹具。网站构建一次，按鉴权配置启动多个隔离实例，整个会话共用。

运行：.venv\\Scripts\\python.exe -X utf8 -m pytest -c tests/pytest.ini tests/web
升级验证：C_NODE_MODULES=<装了新版 next 的 node_modules> 再跑一遍
"""
import pytest

import harness as h

PW, TOKEN = "pw-test:with:colons", "vr_test_token"  # 密码含冒号：Basic 只按第一个冒号切


@pytest.fixture(scope="session")
def build_dir():
    return h.build()


@pytest.fixture(scope="session")
def stub():
    s = h.StubModel()
    yield s
    s.close()


@pytest.fixture(scope="session")
def helper():
    s = h.Helper()
    yield s
    s.close()


@pytest.fixture(scope="session")
def canary():
    """SSRF 金丝雀：和 helper 同为本机服务，但不在放行名单里，被访问即说明服务端请求了不该请求的地址。"""
    s = h.Helper()
    yield s
    s.close()


@pytest.fixture(scope="session")
def sites(build_dir, stub, helper):
    """按需启动：sites("full") 等。同名只启动一次。

    SSRF_ALLOW_HOSTS（B45/B46 修复时约定）只放行 helper 和回调重试用的死端口，
    回调 / 下载类用例在 SSRF 修好后照常能跑；canary 不在名单里，SSRF 用例拿它当靶子。"""
    # 限流（B67）只在 burst 实例上按默认值生效，其余实例放宽，免得共用实例的大量提交互相挤占
    allow = {"SSRF_ALLOW_HOSTS": f"127.0.0.1:{helper.port},127.0.0.1:9", "RATE_LIMIT_BURST": "100000"}
    envs = {
        "full": {"SITE_PASSWORD": PW, "SITE_API_TOKEN": TOKEN, "MAX_RUNNING": "2"},
        "pw": {"SITE_PASSWORD": PW},
        "token": {"SITE_API_TOKEN": TOKEN},
        "none": {},
        "queue": {"SITE_API_TOKEN": TOKEN, "MAX_RUNNING": "1"},
        "burst": {"SITE_API_TOKEN": TOKEN, "MAX_RUNNING": "2", "RATE_LIMIT_BURST": None},
        "nopython": {"SITE_API_TOKEN": TOKEN, "PYTHON": str(h.TMP / "no-such-python.exe")},
    }
    started = {}

    def get(name):
        if name not in started:
            started[name] = h.Site(build_dir, {**allow, **envs[name]}, stub.url("/chat/completions"), name=name).start()
        return started[name]

    yield get
    for s in started.values():
        s.stop()


@pytest.fixture(scope="session")
def site(sites):
    return sites("full")


class Api:
    """带 Token 的接口客户端。"""

    def __init__(self, s):
        self.s = s

    def __call__(self, method, path, body=None, headers=None, auth=True, **kw):
        hd = {**(h.bearer(TOKEN) if auth else {}), **(headers or {})}
        return self.s.request(method, path, headers=hd, body=body, **kw)

    def submit(self, body=None, stage="creative", **kw):
        b = {"stage": stage, "content": "测试材料", "runs": 1, **(body or {})}
        return self("POST", "/api/v1/reviews", b, **kw)

    def wait(self, id, timeout=60):
        def done():
            j = self("GET", f"/api/v1/reviews/{id}").json()
            return j if j["status"] in ("done", "error") else None
        j = h.wait_for(done, timeout)
        assert j, f"任务 {id} {timeout} 秒内未结束"
        return j


@pytest.fixture(scope="session")
def api(site):
    return Api(site)


@pytest.fixture(scope="session")
def done_job(api):
    """一个已完成的创意评审任务，供只读用例共用。"""
    r = api.submit({"title": "共享任务", "content": "共享材料"})
    assert r.status == 202, r
    j = api.wait(r.json()["id"])
    assert j["status"] == "done", j
    return j
