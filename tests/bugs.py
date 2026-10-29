"""已知缺陷登记表。

测试用 @bug("Bxx") 标记期望行为尚未实现的用例：它们按 xfail(strict=True) 运行，
缺陷修复后用例会变成 XPASS 并报失败，提醒删除标记。每条都要写清楚预期行为。

2026-10-29 已修复除 B28、B41 外的全部缺陷，对应用例已去掉标记、按普通用例运行；条目保留作历史记录（编号不复用）。
B28、B41 是基准数据集的覆盖缺口，要改 build_dataset.py 并重新生成数据集（约 860MB 图片视频），仍未修。
"""

OPEN = {"B28", "B41"}
import pytest

BUGS = {
    "B01": "文件读写未指定编码：非 UTF-8 区域设置（如 Windows 中文版 cp936）下读 rubrics.json / job.json 直接报错",
    "B02": "红线判定为『命中』后自动驳回，但没有进入 needs_human_review（框架文档：红线必须人审）",
    "B03": "evidence / issues / summary / top_fixes 固定取第 0 次采样，与多次采样的均分可能矛盾",
    "B04": "JSON 浮点分数 4.0 被当成缺失丢弃（str(4.0).isdigit() 为 False）",
    "B05": "非整数 / 负数 / 文字分数被静默丢弃，不提示人审",
    "B06": "越界分数（0、6、9）被直接计入总分",
    "B07": "维度缺失或整次采样无效时不提示：总分按剩余权重重新归一，可能把弱项『藏掉』后判通过；模型全部失效时报『驳回 0 分』",
    "B08": "红线 hit 为字符串 \"true\" 或 1 时被当作未命中（代码用 `is True`）",
    "B09": "模型返回 choices 为空或 content 为 null 时抛 IndexError/TypeError，不重试",
    "B10": "响应阶段的网络异常不在重试范围内：读超时 TimeoutError、对端断开 RemoteDisconnected、"
           "连接重置 ConnectionResetError、响应体不完整 IncompleteRead 都不是 URLError 的子类",
    "B11": "模型输出 JSON 合法但缺少 dimensions/redlines 时不校验，聚合阶段 KeyError 崩溃",
    "B12": "最后一次重试失败后仍然 sleep，白白多等 4 秒",
    "B13": "视频文件损坏 / 为空 / 不存在 / 只有音频时 probe_video 不报错，返回残缺参数（含误导性的『无音轨』）",
    "B14": "忽略旋转元数据：手机竖拍（编码为横向 + rotation 90）被判成横屏",
    "B15": "extract_frames 在 n=0（--frames 0）时除零崩溃",
    "B16": "GBK / UTF-16 / 二进制文件被按 UTF-8 + errors=replace 读取，乱码静默送入模型",
    "B17": "Markdown 报告表格未转义 | 和换行，证据里出现这些字符会破坏表格",
    "B18": "技术参数为 0（如响度范围 0.0 LU）时报告显示成『无』",
    "B19": "权重百分比用 int(w*100) 截断，0.29 显示成 28%",
    "B20": "基准评分 score() 不读标签里的 verdict_not 字段。现有 124 个带该字段的都是单红线用例，"
           "红线召回成功必然驳回、失败本来就判失败，所以对现有数据结果无影响；"
           "一旦质量用例开始使用该字段就会漏判",
    "B21": "qwk() 遇到 1..k 范围外的分数时静默错位（0 被计入第 5 类）或 IndexError",
    "B22": "音轨比视频长时，尾帧时间点超出视频流，CTA 尾帧静默丢失",
    "B23": "视频评审框架.md 与 rubrics.json 不一致",
    "B26": "材料分隔符『===== 文件：x =====』是固定文本，材料内容可以伪造文件边界（提示词注入的入口）",
    "B27": ".env 解析不处理引号和行首空格：DEEPSEEK_API_KEY=\"sk-…\" 会把引号带进 key",
    "B28": "基准集覆盖缺口：有红线 / 维度没有任何注入用例",
    "B29": "human_agreement 用 round() 把模型均分取整，2.5→2、3.5→4（银行家舍入），一致率有系统偏差",
    "B30": "同一次采样里重复列出同一条红线会被重复计票：1 次采样说命中就能凑成 2/3『命中』",
    "B31": "红线在所有采样里都没被判（id 写成 r1 / 漏写）时静默算『未命中』，不提示人审",
    "B32": "JSON 从第一个 { 开始解析：模型在 JSON 前的说明文字里出现 { 时整次调用失败",
    "B33": "CLI 不校验 --runs / --frames：--runs 0 在线程池里崩出 ValueError，--frames -1 被静默接受并照常调用模型",
    "B34": "不变性阈值 abs(v - b) <= 0.3 有浮点误差：|Δ| 恰好 0.30 的部分组合（如 1.0→1.3、1.5→1.8）被判不通过",
    "B35": "多个视频一起评审时 tech 被循环覆盖，只有最后一个视频的技术参数进入返回值和报告",
    "B36": "红线用例额外命中了未注入的红线时不计误报、不进失败清单（只有 no_redline 用例才统计误报）",
    "B37": "基准用例或其基准样本的结果缺失时静默跳过，样本量悄悄变小，报告里看不出缺了多少",
    "B38": "质量用例的第 2 个及以后的目标维度均分为 None 时，score() 抛 TypeError",
    "B39": "框架文档要求 V3、V4 结论必须人审，代码没有把它们放进 needs_human_review",
    "B40": "框架文档要求机审『驳回』后转法务/品牌复核，代码没有任何标记",
    "B41": "基准集结构缺口：成片没有不变性变体（如换容器重编码、改码率），格式偏差在成片关测不到",
    # ---- C 层（网站 / 接口 / 安全）----
    "B42": "SITE_PASSWORD 与 SITE_API_TOKEN 都没配置时整站放行（应拒绝所有请求）",
    "B43": "CVE-2025-29927：请求头 x-middleware-subrequest 可绕过 middleware 鉴权（next < 15.2.3）",
    "B44": "依赖版本含已知高危漏洞：next 15.1.6 / react 19.0.0（CVE-2025-29927、CVE-2025-55182/66478 RSC 远程代码执行）。"
           "升级注意：next ≥15.5 有 middleware 时请求体默认只保留前 10MB，必须在 next.config 里设 "
           "experimental.middlewareClientMaxBodySize: \"210mb\"，否则大文件 JSON 上传被截断成 invalid_body",
    "B45": "SSRF：files[].url 可以指向回环 / 内网 / 链路本地地址（含 127.1、2130706433、[::ffff:127.0.0.1] 等写法），"
           "服务端会去下载；跳转后也不重新检查。修复时请支持 SSRF_ALLOW_HOSTS（逗号分隔、按 URL 里的 host:port 原样匹配），"
           "测试用它放行本机辅助服务，回调 / 下载类用例才能继续跑",
    "B46": "SSRF：callback_url 可以指向回环 / 内网地址，任务结束后服务端会 POST 过去（放行名单同 B45）",
    "B47": "/media/jobs/<id>/ 暴露 job.json、status.json、log.txt（含服务器绝对路径、回调地址、异常堆栈），应只开放 inputs/ 与 report.md",
    "B48": "JSON 请求体没有大小上限：超过 210MB 也会整体读入内存再解析",
    "B49": "content / context / transcript 文本不计入 150MB 上限，可以写入任意大的文件",
    "B50": "URL 下载在没有 Content-Length（分块传输）时先把整个响应读进内存再判断大小，不会在超过 150MB 时中止",
    "B51": "PYTHON 不存在时 spawn 的 error 事件没有处理：任务一直停在 running 并占住队列名额",
    "B52": "/media 路径含非法 % 编码时 decodeURIComponent 抛错，返回 500",
    "B53": "Range 超出文件长度时（bytes=-<大于文件>、bytes=0-<大于文件>）返回 500 / 416，按 RFC 9110 应截断到文件末尾返回 206",
    "B54": "nginx client_max_body_size 160m：150MB 文件经 base64 后约 200MB，JSON 接口按文档上传会被 nginx 拒绝",
    "B55": "nginx 没有清除 x-middleware-subrequest 请求头（CVE-2025-29927 的纵深防御）",
    "B56": "serve.sh 用 -H 0.0.0.0 监听，绕过 nginx 直接对外暴露 3100 端口",
    "B57": "请求体类型不对时返回 500 而不是 400：字段为数字等（content / title / callback_url .trim() 抛 TypeError），"
           "或 JSON 顶层是 null（读 b.stage 抛错）；顶层是 [] / 1 / \"s\" 时被当成缺 stage 报 invalid_stage，应报 invalid_body",
    "B58": "SITE_PASSWORD 含非 ASCII 字符（如中文）时永远登录不上：atob 解出 latin1 字节串，没有按 UTF-8 解码",
    "B59": "API文档.md 错误码表漏了代码实际会返回的 invalid_file_url、invalid_status",
    "B60": "human_agreement export 的配额不等于 --n：基准 3、不变性 1 是写死的，--n < 4 时每关仍导出 4 例；"
           "成片没有不变性变体，少的 1 例不补给质量用例（--n 12 只导出 11 例）",
    "B61": "待标注表的 case_id 和材料路径里带着变体名（如 S01_asset_as_blur、.../S03_creative_cr_extreme/...），"
           "标注员能看出是哪类注入，违背代码注释里『不向标注员暴露变体类型』的盲标要求",
    "B62": "/media 对路由层已解码的路径再 decodeURIComponent 一次，safeName 又不过滤 %：上传 50%off.md 后返回的链接"
           "（…/01_50%25off.md）GET 返回 500；labels%252Ejsonl 这种二次编码能命中 labels.jsonl",
    "B63": "POST /api/v1/benchmark/runs 不校验 Content-Type：text/plain 的 JSON 也照常解析并启动轮次（CSRF 简单请求）",
    "B64": "middleware 不检查 Origin / Sec-Fetch-Site：网页用 Basic Auth，浏览器会给跨站请求自动带凭据，"
           "第三方页面能用 multipart / text/plain 简单请求借登录态提交评审、启动基准（消耗模型费用）",
    "B65": "Range 头无法识别时（items=0-5、bytes=abc、bytes=）返回 206 + 整个文件；RFC 9110 要求忽略不认识的单位返回 200，"
           "无效的 bytes 范围应忽略（200）或拒绝（416）",
    "B66": "content_base64 含非法字符时 Buffer.from(..., 'base64') 静默丢弃，落盘的是残缺文件，应报 400 invalid_body",
    "B67": "没有任何限流：同一凭据连续提交几十个评审都直接排队（每个默认 runs=3 调用付费模型），应在短时间大量提交时返回 429",
    "B68": "用例详情页用 marked 渲染数据集里的 .md，不做 HTML 清洗：原始 HTML 和 javascript: 链接原样输出"
           "（数据集是内部内容，风险低）",
    "B69": "仓库里的 nginx 配置只监听 80，没有 HTTPS 跳转和 HSTS；certbot 执行之前 Basic Auth 密码和 API Token 明文传输，"
           "且线上实际配置不在版本库里，无法复核",
}


def bug(bug_id):
    assert bug_id in BUGS, f"未登记的缺陷 {bug_id}"
    assert bug_id in OPEN, f"{bug_id} 已修复，不要再用 @bug 标记"
    return pytest.mark.xfail(strict=True, reason=f"{bug_id}: {BUGS[bug_id]}")
