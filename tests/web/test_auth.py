"""C1 鉴权：配置组合 × 凭据形式 × 路径类型，以及 CVE-2025-29927。"""
import pytest

import harness as h
from conftest import PW, TOKEN

API, PAGE, MEDIA = "/api/v1/rubrics", "/rubric", "/media/dataset/labels.jsonl"
GOOD = {
    "bearer": h.bearer(TOKEN),
    "x-api-key": {"X-API-Key": TOKEN},
    "basic": h.basic(PW),
    "basic-any-user": h.basic(PW, user="随便"),
}
BAD = {
    "none": {},
    "bearer-wrong": h.bearer("vr_wrong"),
    "bearer-lowercase": {"Authorization": f"bearer {TOKEN}"},
    "bearer-token-prefix": h.bearer(TOKEN[:-1]),
    "token-as-basic-pw": h.basic(TOKEN),
    "pw-as-bearer": h.bearer(PW),
    "basic-wrong": h.basic("wrong"),
    "basic-pw-prefix": h.basic(PW[:-1]),
    "basic-garbage": {"Authorization": "Basic !!!"},
    "basic-empty": {"Authorization": "Basic "},
    "x-api-key-empty": {"X-API-Key": ""},
}


@pytest.mark.parametrize("path", [API, PAGE, MEDIA, "/api/v1/reviews", "/jobs", "/"])
@pytest.mark.parametrize("cred", GOOD)
def test_good_credentials_accepted(sites, cred, path):
    assert sites("full").request("GET", path, headers=GOOD[cred]).status == 200


@pytest.mark.parametrize("path", [API, PAGE, MEDIA, "/api/v1/reviews/x", "/api/v1/openapi.json", "/jobs", "/"])
@pytest.mark.parametrize("cred", BAD)
def test_bad_credentials_rejected(sites, cred, path):
    assert sites("full").request("GET", path, headers=BAD[cred]).status == 401


@pytest.mark.parametrize("method", ["POST", "DELETE", "PUT", "PATCH"])
def test_write_methods_need_auth(site, method):
    assert site.request(method, "/api/v1/reviews/20260101-deadbeef", body={}).status == 401


def test_api_401_is_json_page_401_prompts_basic(site):
    r = site.request("GET", API)
    assert r.json()["error"]["code"] == "unauthorized" and "www-authenticate" not in r.headers
    r = site.request("GET", PAGE)
    assert r.headers["www-authenticate"].startswith("Basic ")


@pytest.mark.parametrize("cfg,cred,ok", [
    ("pw", "basic", True), ("pw", "bearer", False), ("pw", "x-api-key", False),
    ("token", "bearer", True), ("token", "x-api-key", True), ("token", "basic", False),
])
def test_single_credential_configs(sites, cfg, cred, ok):
    assert (sites(cfg).request("GET", API, headers=GOOD[cred]).status == 200) is ok


@pytest.mark.parametrize("cfg", ["pw", "token"])
def test_unset_credential_cannot_be_matched_by_empty(sites, cfg):
    """只配了一种时，另一种为空：空 Token / 空密码不能凑成匹配。"""
    for hd in ({"Authorization": "Bearer "}, {"X-API-Key": ""}, h.basic(""), {"Authorization": "Bearer undefined"}):
        assert sites(cfg).request("GET", API, headers=hd).status == 401, hd


@pytest.mark.parametrize("path", [API, PAGE, MEDIA])
def test_unconfigured_site_denies(sites, path):
    assert sites("none").request("GET", path).status == 401


def test_static_assets_are_public(site):
    """_next/static 与 favicon 不鉴权（matcher 排除）：只能拿到构建产物，不能借道访问别的路径。"""
    assert site.request("GET", "/favicon.ico").status != 401
    for p in ("/_next/static/../../api/v1/rubrics", "/_next/static/%2e%2e/%2e%2e/api/v1/rubrics",
              "/favicon.ico/../api/v1/rubrics", "/_next/static/..%2f..%2fapi/v1/rubrics"):
        r = site.request("GET", p)
        assert r.status in (400, 401, 404), (p, r)
        assert "dimensions" not in r.text, p


@pytest.mark.parametrize("path", [API, PAGE, MEDIA])
def test_cve_2025_29927_middleware_subrequest_bypass(site, path):
    # next 15.x 的递归保护：同名 middleware 出现 5 次即跳过 middleware；middleware.js 在根目录，名字就是 "middleware"
    r = site.request("GET", path, headers={"x-middleware-subrequest": ":".join(["middleware"] * 5)})
    assert r.status == 401, f"带 x-middleware-subrequest 绕过了鉴权：{r}"


@pytest.mark.parametrize("value", ["middleware", "middleware:middleware", "src/middleware:" * 5])
def test_subrequest_header_below_depth_still_needs_auth(site, value):
    assert site.request("GET", API, headers={"x-middleware-subrequest": value}).status == 401


def test_non_ascii_password(build_dir, stub):
    """浏览器按 UTF-8 编码 Basic 凭据；atob 解出的是逐字节的 latin1 串，中文密码永远对不上。"""
    s = h.Site(build_dir, {"SITE_PASSWORD": "密码ab"}, stub.url(), name="utf8pw").start()
    try:
        assert s.request("GET", API, headers=h.basic("密码ab")).status == 200
    finally:
        s.stop()


CROSS_SITE = [
    {"Origin": "https://evil.example"},
    {"Origin": "null"},
    {"Sec-Fetch-Site": "cross-site"},
    {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"},
]


def _csrf_form():
    return h.multipart([("stage", None, b"creative"), ("runs", None, b"1"), ("title", None, b"__crash__"),
                        ("content", None, "跨站提交".encode())])


@pytest.mark.parametrize("hd", CROSS_SITE, ids=lambda d: ",".join(f"{k}={v}" for k, v in d.items()))
def test_cross_site_write_with_basic_auth_rejected(site, hd):
    """浏览器会给跨站请求自动带 Basic 凭据：第三方页面的 multipart 表单 / text/plain 是简单请求，不触发预检。"""
    body, ctype = _csrf_form()
    r = site.request("POST", "/api/v1/reviews", headers={**h.basic(PW), **hd, "Content-Type": ctype}, body=body)
    assert r.status == 403, r
    r = site.request("POST", "/api/v1/benchmark/runs", headers={**h.basic(PW), **hd, "Content-Type": "text/plain"},
                     body='{"name": "csrf", "split": "dev", "stages": ["asset"], "dry_run": true}')
    assert r.status in (403, 415), r


@pytest.mark.parametrize("hd", [{}, {"Sec-Fetch-Site": "same-origin"}, {"Sec-Fetch-Site": "none"}],
                         ids=["no-origin", "same-origin", "user-typed"])
def test_same_site_write_with_basic_auth_accepted(site, hd):
    """对照：同源页面、命令行（不带 Origin）都要能正常提交，修 B64 时不能一刀切。"""
    body, ctype = _csrf_form()
    hd = {**hd, **({"Origin": f"http://127.0.0.1:{site.port}"} if hd.get("Sec-Fetch-Site") == "same-origin" else {})}
    r = site.request("POST", "/api/v1/reviews", headers={**h.basic(PW), **hd, "Content-Type": ctype}, body=body)
    assert r.status == 202, r


def test_cross_site_with_bearer_is_not_csrf(site):
    """Bearer / X-API-Key 浏览器不会自动带，跨站来源也应照常放行（脚本调用接口的场景）。"""
    body, ctype = _csrf_form()
    r = site.request("POST", "/api/v1/reviews", headers={**h.bearer(TOKEN), "Origin": "https://evil.example",
                                                          "Content-Type": ctype}, body=body)
    assert r.status == 202, r


def test_cve_probe_control(site):
    """对照：不带攻击头时同样的请求确实是 401，上面的用例不是因为路由本身公开才通过。"""
    assert site.request("GET", API).status == 401
