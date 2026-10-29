"""框架自检：实例能启动、鉴权生效、任务能经模型桩跑完。这些失败时其余 C 层用例都不可信。"""


def test_site_up_and_auth_enforced(site, api):
    assert site.request("GET", "/api/v1/rubrics").status == 401
    assert api("GET", "/api/v1/rubrics").status == 200


def test_job_runs_through_stub(done_job, stub):
    assert done_job["result"]["verdict"] == "通过"
    assert done_job["result"]["total"] == 4
    assert any("共享材料" in c for c in stub.calls), "工作进程没有打到模型桩"


def test_no_real_outbound(api):
    """/health 会查 DeepSeek 余额：必须被不可达代理挡住，而不是真的出网。"""
    b = api("GET", "/api/v1/health").json()
    assert b["deepseek_balance"]["available"] is None and b["deepseek_balance"].get("error")
