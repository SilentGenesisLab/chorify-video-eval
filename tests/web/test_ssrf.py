"""C7 服务端发起的请求：files[].url 下载与 callback_url。

期望：拒绝回环 / 内网 / 链路本地地址，跳转后重新检查；没有 Content-Length 时边读边计数，超过 150MB 立即中止。

靶子是 canary（本机服务、不在 SSRF_ALLOW_HOSTS 里）：只要它被访问，就说明服务端请求了不该请求的地址。
helper 在放行名单里，用来测下载 / 回调的正常逻辑，SSRF 修好后这些用例照常能跑。
断言错误码而不只是 400：内网地址经不可达代理会『下载失败』，那也是 400，但不是 SSRF 拦截。
"""
import time

import pytest

import harness as h

LOOPBACK_FORMS = ["127.0.0.1", "localhost", "127.1", "2130706433", "0x7f000001", "127.000.000.001",
                  "0.0.0.0", "[::1]", "[::ffff:127.0.0.1]", "[::ffff:7f00:1]"]
INTERNAL = ["10.0.0.1", "172.16.0.1", "172.31.255.254", "192.168.1.1", "169.254.169.254", "100.64.0.1", "[fd00::1]",
            "[fe80::1]"]


def canary_hits(canary, tag):
    return [p for p in canary.canary if tag in p]


def submit_url(api, url, stage="creative", **kw):
    return api.submit({"title": "__crash__", "content": "", "files": [{"name": "a.png", "url": url}]}, stage=stage, **kw)


def code(r):
    return r.status, (r.json().get("error") or {}).get("code")


@pytest.mark.parametrize("host", LOOPBACK_FORMS)
def test_file_url_to_loopback_rejected(api, canary, host):
    tag = f"direct-{host}-{time.time_ns()}"
    r = submit_url(api, f"http://{host}:{canary.port}/canary/{tag}")
    assert code(r) == (400, "invalid_file_url"), r
    assert not canary_hits(canary, tag)


@pytest.mark.parametrize("host", INTERNAL)
def test_file_url_to_internal_rejected(api, host):
    assert code(submit_url(api, f"http://{host}:8080/a.png")) == (400, "invalid_file_url")


def test_file_url_redirect_to_loopback_rejected(api, helper, canary):
    """首跳是放行名单里的 helper，302 到不在名单里的 canary：只查首跳的实现会放过去。"""
    tag = f"redir-{time.time_ns()}"
    target = canary.url(f"/canary/{tag}")
    r = submit_url(api, helper.url(f"/redirect?to={target}"))
    assert not canary_hits(canary, tag), "跳转后没有重新检查"
    assert code(r) == (400, "invalid_file_url"), r


def test_allowed_host_redirect_to_allowed_host_works(api, helper):
    """对照：跳转本身不应被一刀切禁止。"""
    r = submit_url(api, helper.url(f"/redirect?to={helper.url('/file/ok.png')}"))
    assert r.status == 202, r


@pytest.mark.parametrize("host", LOOPBACK_FORMS + INTERNAL)
def test_callback_to_internal_rejected(api, host):
    r = api.submit({"title": "__crash__", "callback_url": f"http://{host}:8080/hook"})
    assert code(r) == (400, "invalid_callback_url"), r


def test_chunked_download_aborts_after_limit(api, helper):
    """无 Content-Length 的 400MB 分块响应：服务端必须在读到约 150MB 时中止并报 413。"""
    before = helper.chunked_sent
    r = submit_url(api, helper.url("/chunked/400/big.mp4"), stage="video", timeout=300)
    sent = helper.chunked_sent - before
    assert code(r) == (413, "too_large"), r
    assert sent < 200 * 1024 * 1024, f"服务端读了 {sent >> 20}MB 才停"


def test_declared_oversize_download_rejected_early(api, helper):
    """Content-Length 声明 400MB：看响应头就该拒绝，不读响应体。"""
    before = helper.sized_sent
    r = submit_url(api, helper.url("/sized/400/big.mp4"), stage="video", timeout=120)
    assert code(r) == (413, "too_large"), r
    time.sleep(1)
    assert helper.sized_sent - before < 100 * 1024 * 1024, f"服务端读了 {(helper.sized_sent - before) >> 20}MB"


def test_url_download_succeeds(api, site, helper):
    r = submit_url(api, helper.url("/file/kv.png"))
    assert r.status == 202, r
    saved = site.jobs / r.json()["id"] / "inputs"
    assert [p.read_bytes() for p in saved.iterdir()] == [b"\x89PNG\r\n\x1a\nfile"]


def test_url_download_failure_is_400(api, helper):
    assert code(submit_url(api, helper.url("/missing"))) == (400, "file_download_failed")
