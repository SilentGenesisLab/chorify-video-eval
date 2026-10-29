# 视频评审台 · A / B / C 三层评测报告

日期：2026-10-28 · 被测版本：`main` @ `e922701` · 产品代码未改动（测试只登记缺陷，不修）

| 层              | 测什么                                              | 结果                                                                  |
| -------------- | ------------------------------------------------ | ------------------------------------------------------------------- |
| A 确定性层         | `video_review.py` 的聚合、调用重试、视频探测、取帧、提示词、报告，以及基准工具 | 219 passed · 86 xfailed · `video_review.py` 行覆盖 99% · 变异体 33/33 被杀死 |
| B 模型判断层        | 真实调用 DeepSeek：红线召回、误报、灵敏度、不变性、稳定性、标注一致性、证据、注入    | 507 例 × 3 次采样 + 72 例复测，0 失败 · 门槛 34/40 通过                           |
| C 网站 / 接口 / 安全 | Next.js 站点：鉴权、提交校验、任务、/media、只读接口、SSRF、部署配置、依赖漏洞 | 319 passed · 90 xfailed                                             |
| 全量             | `pytest tests`                                   | **598 passed · 29 skipped · 176 xfailed · 0 failed**（146 秒）         |

- **xfailed**：已登记缺陷（`tests/bugs.py`，B01–B69，没有 B24/B25，共 67 条），按 `xfail(strict=True)` 运行。修好一个缺陷后对应用例会 XPASS 并报失败，提醒删掉标记。
- **skipped**：B 层门槛测试，只在设置 `VR_BENCH_METRICS` 时运行。

## 修复状态（2026-10-29）

67 条缺陷已修 65 条，对应用例去掉了 xfail 标记，按普通用例运行。修复后全量 **811 passed · 85 skipped · 4 xfailed · 0 failed**；变异体 43 个全部被杀死（新增 10 个，覆盖修复后的规则）。

- **还没修：** B28、B41，基准数据集的覆盖缺口。要改 `build_dataset.py` 并重新生成约 860MB 的图片和视频。
- **结论变化：** 用评测当时的 rubrics 重新聚合 B 层第一轮的 507 例，结论和总分全部不变。修复只影响异常输入，正常输出的判定不变。
- **新增的结论值：** 有维度在所有采样里都没有有效分数时，结论为"无法判定（评审输出不完整）"。总分按全部权重计算，不再重新归一。
- **人审标记：** `needs_human_review` 现在还包括命中的红线、漏判的红线、无效分数、成片 V3/V4，以及驳回时的"驳回复核"。每一项的原因在新字段 `review_reasons` 里。
- **部署前要做：**
  - 配好 TLS 证书再重载 nginx。
  - 在 `review-site` 执行 `npm ci`（next 15.5.28、react 19.0.9）。
  - 确认 `SITE_PASSWORD` 或 `SITE_API_TOKEN` 已设置，否则整站拒绝访问。
- **新增可选配置：** `SSRF_ALLOW_HOSTS`、`RATE_LIMIT_BURST`、`RATE_LIMIT_PER_MINUTE`，见 `review-site/.env.sample`。

下面是修复前的评测结果。

## 结论

1. **安全问题最急，不建议在修复前对公网开放。**
   - 依赖有已知高危漏洞：next 15.1.6 的中间件鉴权可绕过（CVE-2025-29927），react 19.0.0 有 RSC 远程代码执行。
   - 没配置凭据时整站放行。
   - 服务端会去下载或回调任意内网地址（SSRF）。
   - 浏览器跨站请求能借登录态提交评审、消耗模型费用（CSRF）。
   - 3100 端口绕过 nginx 直接对外，nginx 也没有 HTTPS。
2. **评审结果的解析和人审有漏洞。**
   - 模型输出 `4.0` 被当成缺失（B04），`"true"` 被当成未命中（B08）。
   - 维度缺失时按剩余权重重新归一，弱项可能被"藏掉"后判通过（B07）。
   - 红线命中后自动驳回，但不进人审（B02），和框架文档要求不符。
3. **模型本身的判断，红线可靠、打分尺度需要校准。**
   - 红线召回 98.9%，隐蔽红线 100%，陷阱误报 2.1%，注入伪造审核结论不影响召回。
   - 分镜关打分比 Claude 标注（非人工）低约 1 分（QWK 0.25）。
   - 总分在 3.0 及格线附近（约 2.8–3.2）时，判定会随重新采样、格式、套话翻转。

## A 层：确定性层

用本地桩服务器代替模型接口，用参数已知的合成视频核对测量值。不联网、不花钱。

| 文件 | 范围 | passed | xfailed |
|---|---|---|---|
| `test_aggregate.py` | 多次采样 → 均分、红线投票、总分、结论、人审标记 | 60 | 21 |
| `test_call_model.py` | 请求体、响应解析、重试与停止条件 | 24 | 11 |
| `test_probe.py` | 分辨率、时长、帧率、响度、黑帧、冻结、旋转 | 25 | 5 |
| `test_frames.py` | 取帧时间点、尾帧、缩放、边界时长 | 11 | 2 |
| `test_prompt.py` | 提示词完整性、材料原样送入、文件边界 | 13 | 7 |
| `test_report.py` | Markdown 报告内容与表格结构 | 5 | 4 |
| `test_pipeline.py` | evaluate、网站 worker、.env 串联 | 12 | 10 |
| `test_encoding.py` | 非 UTF-8 区域设置（子进程 cp936） | 1 | 5 |
| `test_rubric_consistency.py` | rubrics.json 合法性、与框架文档一致、标签完整 | 26 | 7 |
| `test_benchmark_metrics.py` | score()、qwk()、kappa()、agree() | 15 | 10 |
| `test_benchmark_tools.py` | 待标注表导出、load_labels、run_all | 27 | 4 |
| **合计** | | **219** | **86** |

**覆盖率**（pytest-cov）：

| 文件 | 行覆盖 |
|---|---|
| `video_review.py` | 99%（225 行缺 3 行） |
| `run_benchmark.py` | 90% |
| `human_agreement.py` | 89% |
| `build_dataset.py` | 0%，数据生成脚本，不在测试范围 |

**变异测试**（`tests/mutate.py`）：往 `video_review.py` 的副本里逐个注入 33 种典型错误，例如阈值 `>=` 改 `>`、红线多数票改 `>=`、去掉尾帧、温度改 0.7、`.env` 优先于环境变量。33 个全部被测试发现（杀死），没有存活的。

## B 层：模型判断层

详细数字、费用和复现命令见 `tests/bench/FINAL_REPORT.md`，逐例结果见 `tests/bench/results/b1/r1/report.md`。

- **被测：** `video_review.evaluate`，模型 deepseek-flash，effort=high，每例 3 次采样。
- **数据：** 测试集 315 例（场景 S03–S08，四关），加探针 192 例。探针包括陷阱、隐蔽红线、梯度序列、提示词注入和偏差变体。
- **评分器：** 独立实现聚合与指标，不复用 `run_benchmark.score`（它有 B20、B34、B36–B38），并且和产品的 `aggregate` 逐例对比。评分器自身有 60 条单元测试（`test_scoring.py`）。

| 项 | 结果 | 门槛 |
|---|---|---|
| B1 红线召回 | 98.9%（92/93）；隐蔽红线 100%（36/36） | 过 |
| B2 误报 | 无红线用例 3.2%（7/222）；陷阱 2.1%（1/48） | 过 |
| B3 缺陷灵敏度 | 94.0%（158/168）；梯度序列 24/24 单调 | 过 |
| B4 不变性 | 88.9%（64/72）；加套话时判定翻转 17% | 过 |
| B5 稳定性 | 单例维度极差 ≥2 的占 0.3%；两轮重跑判定一致 94.4% | 过 |
| B6 标注一致性（Claude 标注，非人工） | 创意 QWK 0.61；分镜 QWK 0.25，±1 内 69% | **不过（4 条）** |
| B7 证据可核验 | 严格 76.5%，宽松 82.4%；1 处引用不存在的镜号 | **不过（1 条）** |
| B8 注入抵抗 | 红线召回 100%；总分 −0.05；2/36 判定由驳回变通过 | **不过（1 条）** |
| 聚合一致性 | 独立聚合与产品 aggregate 507/507 一致 | 过 |

**费用：** 实际约 ¥49–74。运行期间账户充值，r1 第二段的余额差失效，所以给的是区间。精确数字请看 DeepSeek 控制台的用量账单。

## C 层：网站 / 接口 / 安全

网站构建一次，按不同鉴权配置启动多个隔离实例，模型调用由桩服务器代替。

| 文件 | 范围 | passed | xfailed |
|---|---|---|---|
| `web/test_smoke.py` | 实例能启动、鉴权生效、任务能跑完 | 3 | 0 |
| `web/test_auth.py` | C1 鉴权：配置组合 × 凭据形式 × 路径类型，CVE-2025-29927 | 123 | 11 |
| `web/test_submit.py` | C2 提交校验：每条规则的边界、错误码、落盘文件名 | 53 | 16 |
| `web/test_jobs.py` | C3/C4 任务：状态流转、排队并发、删除、回调、重启恢复 | 27 | 1 |
| `web/test_read.py` | C5 只读接口与页面、C8 OpenAPI 与路由一致、基准轮次 | 48 | 5 |
| `web/test_media.py` | C6 /media：白名单、路径穿越、双重解码、Range | 38 | 13 |
| `web/test_ssrf.py` | C7 服务端请求：files[].url 下载与 callback_url | 4 | 38 |
| `web/test_deploy.py` | C9 部署配置静态检查、C10 依赖漏洞 | 23 | 6 |
| **合计** | | **319** | **90** |

- **升级验证：** 用 next 15.5.28 + react 19.0.9 跑，并在 next.config 里加 `experimental.middlewareClientMaxBodySize`，B43、B44 变为 XPASS。不加这项配置时，150MB 上传会被截断到 10MB，这是一个回归。
- **生产服务器：** 只做过只读的版本检查，没有任何改动。

## 缺陷清单（67 条，按严重程度）

完整描述见 `tests/bugs.py`。A 层 41 条（B01–B41 和 B60、B61），C 层 26 条（B42–B59、B62–B69）。

### 高：安全，或会导致错误结论

| 编号 | 问题 |
|---|---|
| B42 | SITE_PASSWORD 与 SITE_API_TOKEN 都没配置时整站放行 |
| B43 / B44 | next 15.1.6 中间件鉴权可绕过（CVE-2025-29927）；react 19.0.0 RSC 远程代码执行 |
| B45 / B46 | SSRF：files[].url 与 callback_url 可指向回环、内网地址，跳转后不重新检查 |
| B63 / B64 | CSRF：不校验 Content-Type、Origin；跨站页面能借 Basic Auth 登录态提交评审、启动基准 |
| B56 | serve.sh 监听 0.0.0.0，3100 端口绕过 nginx 直接对外 |
| B69 | nginx 只监听 80，没有 HTTPS 和 HSTS，密码与 Token 明文传输 |
| B47 | /media 暴露 job.json、status.json、log.txt（服务器路径、回调地址、堆栈） |
| B67 | 没有限流：一个凭据能连续提交几十个付费评审 |
| B04 / B08 | 浮点分 4.0 被当缺失；hit 为 "true" 或 1 时被当未命中 |
| B07 | 维度缺失时按剩余权重重新归一，弱项可能被藏掉后判通过；模型全部失效时报"驳回 0 分" |
| B02 / B39 / B40 | 红线命中、V3/V4 结论、机审驳回都没有按框架文档进人审或复核 |
| B26 | 材料分隔符是固定文本，材料内容可以伪造文件边界，是提示词注入的入口 |
| B30 / B31 | 同一采样里重复列出的红线被重复计票；红线漏判时静默算"未命中" |

### 中：稳定性、资源，或会误导结果

| 编号 | 问题 |
|---|---|
| B01 | 读写文件不指定编码，Windows 中文版（cp936）下直接报错 |
| B05 / B06 | 非整数、文字分数被静默丢弃；越界分数（0、6、9）直接计入总分 |
| B09 / B10 / B11 | choices 为空、响应阶段网络异常、缺字段时崩溃或不重试 |
| B32 | JSON 前的说明文字里出现 { 时整次调用失败 |
| B03 | evidence 和 summary 固定取第 0 次采样，可能与均分矛盾 |
| B13 / B14 / B22 / B35 | 坏视频不报错；忽略旋转元数据；音轨更长时尾帧丢失；多视频时 tech 被覆盖 |
| B16 | GBK、UTF-16、二进制文件按 UTF-8 读，乱码静默送进模型 |
| B48 / B49 / B50 / B54 | 请求体、文本字段、分块下载没有大小上限；nginx 160m 挡住 150MB 的 base64 上传 |
| B51 | PYTHON 不存在时任务一直停在 running，并占住队列名额 |
| B52 / B53 / B57 / B62 / B65 / B66 | 各种非法输入返回 500 或残缺文件，应返回 400、206 或 200 |
| B58 | 密码含中文时永远登录不上 |
| B55 | nginx 没有清除 x-middleware-subrequest，缺少纵深防御 |
| B68 | marked 渲染数据集里的 .md 不清洗 HTML（数据是内部内容，风险低） |

### 低：基准工具、文档、显示

| 编号 | 问题 |
|---|---|
| B20 / B21 / B29 / B34 / B36 / B37 / B38 | run_benchmark、human_agreement 的指标计算问题（B 层评分器已独立规避） |
| B28 / B41 | 基准集覆盖缺口：部分红线和维度没有注入用例；成片没有不变性变体 |
| B60 / B61 | 待标注表的配额不等于 --n；case_id 带变体名，不是真正的盲标 |
| B12 / B15 / B33 | 最后一次重试后仍 sleep；--frames 0 除零；CLI 参数不校验 |
| B17 / B18 / B19 | 报告表格不转义 \|；0 值显示成"无"；权重百分比截断 |
| B23 / B59 | 框架文档与 rubrics.json 不一致；API 文档漏了两个错误码 |
| B27 | .env 不处理引号和行首空格 |

## 建议的修复顺序

1. **上线前必须做：**
   - 升级 next / react（B43、B44），同时设置 `middlewareClientMaxBodySize`。
   - 没配凭据时拒绝所有请求（B42）。
   - SSRF 防护（B45、B46）。
   - 校验 Origin 或 Content-Type（B63、B64）。
   - 只监听 127.0.0.1（B56），配好 HTTPS（B69）。
   - 收紧 /media 能访问的文件（B47），加限流（B67）。
2. **评审正确性：**
   - 分数和 hit 的解析（B04–B08）。
   - 维度缺失和红线漏判转人审（B07、B31）。
   - 按框架文档补人审标记（B02、B39、B40）。
   - 材料边界改成随机分隔符（B26）。
3. **模型判断：**
   - 总分在 2.8–3.2 时标"需人审"。
   - 找人工标注复核分镜关的打分尺度（B6）。
   - 创意关 R2（夸大或绝对化用语）误报偏多，可以在提示词里给反例。

## 局限

- **B6 的参照不是人工：** 一致性对照用的是 Claude 盲标的 24 例，只能当粗校准。
- **B 层只覆盖一个模型设置：** 只跑了 deepseek-flash、effort=high，没有对比其他模型或参数。
- **执行顺序只验证了一次：** 用打乱顺序插件跑过全量（种子 1）并通过；没有装 pytest-randomly，也没有试多个种子。
- **变异测试只覆盖产品核心：** 只对 `video_review.py` 做了变异，`run_benchmark.py` 和 `human_agreement.py` 没做。
- **C 层没有覆盖真实流量：** 测的是本地构建的实例；线上 nginx 配置不在版本库里，无法复核（B69）。
- **B 层数据不在仓库里：** png、mp4 不进 git，换机器要先用 `build_dataset.py` 重新生成数据，再用 `probes.py` 生成探针视频。

## 运行方法

```powershell
pip install -r tests/requirements.txt                              # pytest、pytest-cov、hypothesis
.venv/Scripts/python -X utf8 -m pytest -c tests/pytest.ini tests   # 全量，约 2.5 分钟（必须带 -X utf8，见 B01）
.venv/Scripts/python -X utf8 -m pytest -c tests/pytest.ini tests --ignore=tests/web --ignore=tests/bench   # 只跑 A 层，约 1 分钟
.venv/Scripts/python -X utf8 tests/mutate.py                       # 变异测试，约 50 秒
# B 层真实调用见 tests/bench/FINAL_REPORT.md 的"复现"一节
```

## 文件

| 路径 | 内容 |
|---|---|
| `tests/REPORT_ABC.md` | 本报告 |
| `tests/bugs.py` | 缺陷登记表（B01–B69） |
| `tests/test_*.py`、`conftest.py`、`media.py`、`mutate.py` | A 层测试、夹具、合成视频、变异测试 |
| `tests/web/` | C 层测试与网站测试工具（harness） |
| `tests/bench/` | B 层评测代码、门槛、探针、标注、`FINAL_REPORT.md` |
| `tests/bench/results/b1/` | B 层真实运行：r1（507 例）、r2（72 例复测）、`spend.json` |
| `tests/bench/results/test_v1/` | 旧结果的离线复评 |
