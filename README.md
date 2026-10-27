# chorify-video-eval · 视频评审台

用大模型（默认 deepseek-flash，可配置为任意 OpenAI 兼容接口的模型，线上用 claude-opus-5-5）对广告/短视频生产的四道关卡做自动评审：**创意 → 分镜 → 资产 → 成片**。每道关卡先过红线（一票否决），再按加权维度打 1–5 分，结论由程序按规则计算。可以一位评审员多次采样（`sample`），也可以分维度评审团（`panel`）：每位评审员只评自己负责的维度、合规评审员只判红线，并发执行。附带一套构造法基准数据集（420 例）、Next.js 评审网站和 `/api/v1` HTTP 接口。

## 目录

| 路径 | 内容 |
|---|---|
| `视频评审框架.md` | 研究文档：四关审核维度、红线依据（《广告法》、AI 生成内容标识办法、平台规范）、审核方法 |
| `rubrics.json` | 评分标准：各关卡红线、维度、权重、评分锚点 |
| `video_review.py` | 评审器（库 + 命令行）：多次采样、红线多数票、成片技术 QC（黑帧、冻结、响度等） |
| `benchmark/` | 基准数据集构建、评测脚本、迭代记录和评测结果，见 [benchmark/README.md](benchmark/README.md) |
| `review-site/` | Next.js 15 网站与 HTTP 接口 |
| `review-site/docs/API文档.md` | HTTP 接口文档（网站 `/docs` 页面） |
| `review-site/docs/使用手册.md` | 使用指南（网站 `/guide` 页面） |
| `部署文档.md` | 部署流程 |

## 快速开始

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.sample .env        # 填入 DEEPSEEK_API_KEY
.venv/bin/python video_review.py storyboard samples/storyboard_demo.md --runs 1
```

部署网站和接口见 [部署文档.md](部署文档.md)。

## 测试集表现（test_v1，S03–S08，315 例）

| 关卡 | 红线召回 | 误报率 | 缺陷敏感度 |
|---|---|---|---|
| 创意 | 100% | 2% | 98% |
| 分镜 | 100% | 3% | 94% |
| 资产 | 96% | 0% | 83% |
| 成片 | 100% | 0% | 98% |

按用例统计，总体通过率 95%（299/315），费用约 ¥10.8。各项指标的定义和已知弱项见 [benchmark/README.md](benchmark/README.md)。

数据集的标签来自构造方式，不是人工标注，测试集成绩是评审器能力的上限估计。上线前建议用 `benchmark/human_agreement.py` 做一轮人工一致性校准。
