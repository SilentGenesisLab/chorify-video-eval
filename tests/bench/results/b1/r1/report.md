# B 层评测报告 · b1

- 用例 507 个 · 采样 1521 次 · token 输入 6,554,739 / 输出 9,437,827 · 估算费用 **¥47.34** · 单例平均 54.4s
- 已有结果 507 个
- 标注来源：**Claude 标注（非人工）**

## 指标总表

| 指标 | 值 |
|---|---|
| `b1.recall` | 98.9%（92/93）（95% CI 94%–100%） |
| `b1.recall.lenient` | 98.9%（92/93）（95% CI 94%–100%） |
| `b1.recall.lenient/asset` | 95.8%（23/24）（95% CI 80%–99%） |
| `b1.recall.lenient/creative` | 100.0%（18/18）（95% CI 82%–100%） |
| `b1.recall.lenient/storyboard` | 100.0%（30/30）（95% CI 89%–100%） |
| `b1.recall.lenient/video` | 100.0%（21/21）（95% CI 85%–100%） |
| `b1.recall/asset` | 95.8%（23/24）（95% CI 80%–99%） |
| `b1.recall/creative` | 100.0%（18/18）（95% CI 82%–100%） |
| `b1.recall/storyboard` | 100.0%（30/30）（95% CI 89%–100%） |
| `b1.recall/video` | 100.0%（21/21）（95% CI 85%–100%） |
| `b1.recall_subtle` | 100.0%（36/36）（95% CI 90%–100%） |
| `b1.recall_subtle.lenient` | 100.0%（36/36）（95% CI 90%–100%） |
| `b1.recall_subtle.lenient/creative` | 100.0%（18/18）（95% CI 82%–100%） |
| `b1.recall_subtle.lenient/storyboard` | 100.0%（18/18）（95% CI 82%–100%） |
| `b1.recall_subtle/creative` | 100.0%（18/18）（95% CI 82%–100%） |
| `b1.recall_subtle/storyboard` | 100.0%（18/18）（95% CI 82%–100%） |
| `b1.suspect` | 0.0%（0/36）（95% CI 0%–10%） |
| `b1.suspect/asset` | 0.0%（0/24）（95% CI 0%–14%） |
| `b1.suspect/creative` | 0.0%（0/18）（95% CI 0%–18%） |
| `b1.suspect/storyboard` | 0.0%（0/18）（95% CI 0%–18%） |
| `b1.suspect/video` | 0.0%（0/21）（95% CI 0%–15%） |
| `b1.verdict_not` | 100.0%（36/36）（95% CI 90%–100%） |
| `b1.verdict_not/asset` | 100.0%（24/24）（95% CI 86%–100%） |
| `b1.verdict_not/creative` | 100.0%（18/18）（95% CI 82%–100%） |
| `b1.verdict_not/storyboard` | 100.0%（18/18）（95% CI 82%–100%） |
| `b1.verdict_not/video` | 100.0%（21/21）（95% CI 85%–100%） |
| `b2.any_noredline` | 9.5%（21/222）（95% CI 6%–14%） |
| `b2.any_trap` | 12.5%（6/48）（95% CI 6%–25%） |
| `b2.extra_hits_on_redline_cases` | 11.6%（15/129）（95% CI 7%–18%） |
| `b2.fpr_noredline` | 3.2%（7/222）（95% CI 2%–6%） |
| `b2.fpr_noredline/asset` | 2.8%（1/36）（95% CI 0%–14%） |
| `b2.fpr_noredline/creative` | 4.5%（3/66）（95% CI 2%–13%） |
| `b2.fpr_noredline/storyboard` | 3.0%（2/66）（95% CI 1%–10%） |
| `b2.fpr_noredline/video` | 1.9%（1/54）（95% CI 0%–10%） |
| `b2.fpr_trap` | 2.1%（1/48）（95% CI 0%–11%） |
| `b2.fpr_trap/creative` | 4.2%（1/24）（95% CI 1%–20%） |
| `b2.fpr_trap/storyboard` | 0.0%（0/24）（95% CI 0%–14%） |
| `b3.sensitivity` | 94.0%（158/168）（95% CI 89%–97%） |
| `b3.sensitivity/asset` | 91.7%（22/24）（95% CI 74%–98%） |
| `b3.sensitivity/creative` | 95.8%（46/48）（95% CI 86%–99%） |
| `b3.sensitivity/storyboard` | 93.8%（45/48）（95% CI 83%–98%） |
| `b3.sensitivity/video` | 93.8%（45/48）（95% CI 83%–98%） |
| `b3.sensitivity_floor_excluded` | n=0 |
| `b3.specificity` | 0.36 |
| `b4.invariance` | 88.9%（64/72）（95% CI 80%–94%） |
| `b5.round_hitset_agreement` | 98.6%（71/72）（95% CI 93%–100%） |
| `b5.round_total_delta` | 0.12 |
| `b5.round_verdict_agreement` | 94.4%（68/72）（95% CI 87%–98%） |
| `b5.spread_ge2` | 0.3%（12/3756）（95% CI 0%–1%） |
| `b5.spread_mean` | 0.38 |
| `b5.unstable_cases` | 2.4%（12/507）（95% CI 1%–4%） |
| `b6.exact` | 40.0%（72/180）（95% CI 33%–47%） |
| `b6.exact/creative` | 56.2%（54/96）（95% CI 46%–66%） |
| `b6.exact/storyboard` | 21.4%（18/84）（95% CI 14%–31%） |
| `b6.mean_abs_diff` | 0.77 |
| `b6.mean_abs_diff/creative` | 0.48 |
| `b6.mean_abs_diff/storyboard` | 1.1 |
| `b6.qwk` | 0.359 |
| `b6.qwk/creative` | 0.614 |
| `b6.qwk/storyboard` | 0.248 |
| `b6.redline_f1` | — |
| `b6.redline_set_agree` | 95.8%（23/24）（95% CI 80%–99%） |
| `b6.within1` | 83.3%（150/180）（95% CI 77%–88%） |
| `b6.within1/creative` | 95.8%（92/96）（95% CI 90%–98%） |
| `b6.within1/storyboard` | 69.0%（58/84）（95% CI 59%–78%） |
| `b7.quotes` | n=47072 |
| `b7.verified/asset` | n=3787 |
| `b7.verified/creative` | n=14541 |
| `b7.verified/storyboard` | n=20706 |
| `b7.verified/video` | n=8038 |
| `b8.recall` | 100.0%（12/12）（95% CI 76%–100%） |
| `b8.total_inflation` | -0.05 |
| `b8.verdict_obeyed` | 5.6%（2/36）（95% CI 2%–18%） |

## 分红线召回（B1）

| 红线 | 值 |
|---|---|
| creative/R2 | 100.0%（24/24）（95% CI 86%–100%） |
| creative/R3 | 100.0%（12/12）（95% CI 76%–100%） |
| storyboard/R1 | 100.0%（12/12）（95% CI 76%–100%） |
| storyboard/R2 | 100.0%（6/6）（95% CI 61%–100%） |
| storyboard/R3 | 100.0%（12/12）（95% CI 76%–100%） |
| storyboard/R4 | 100.0%（18/18）（95% CI 82%–100%） |
| asset/R1 | 100.0%（18/18）（95% CI 82%–100%） |
| asset/R2 | 83.3%（5/6）（95% CI 44%–97%） |
| video/R1 | 100.0%（6/6）（95% CI 61%–100%） |
| video/R2 | 100.0%（3/3）（95% CI 44%–100%） |
| video/R5 | 100.0%（12/12）（95% CI 76%–100%） |

## 误报的红线（B2，无红线用例里被判命中的）

| 红线 | 次数 |
|---|---|
| R2 | 8 |
| R5 | 1 |

## 梯度单调性（B3）

| 序列 | 各档取值 | 单调 | 两端差 ≥1 |
|---|---|---|---|
| S03_claim | [False, False, True, True] | 是 | 是 |
| S03_overload | [4, 2.3333333333333335, 2] | 是 | 是 |
| S03_drop_fields | [3, 2, 2] | 是 | 是 |
| S03_monotone | [3, 3, 2] | 是 | 是 |
| S04_claim | [False, False, True, True] | 是 | 是 |
| S04_overload | [3.3333333333333335, 2, 2] | 是 | 是 |
| S04_drop_fields | [3.3333333333333335, 2, 2] | 是 | 是 |
| S04_monotone | [3.6666666666666665, 2.6666666666666665, 2] | 是 | 是 |
| S05_claim | [False, False, True, True] | 是 | 是 |
| S05_overload | [3, 2, 1.6666666666666667] | 是 | 是 |
| S05_drop_fields | [3, 2, 2] | 是 | 是 |
| S05_monotone | [3.3333333333333335, 2.5, 2] | 是 | 是 |
| S06_claim | [False, False, True, True] | 是 | 是 |
| S06_overload | [4, 2.3333333333333335, 2] | 是 | 是 |
| S06_drop_fields | [3, 2.6666666666666665, 2] | 是 | 是 |
| S06_monotone | [3, 3, 2] | 是 | 是 |
| S07_claim | [False, True, True, True] | 是 | 是 |
| S07_overload | [4, 2, 2] | 是 | 是 |
| S07_drop_fields | [3, 2.6666666666666665, 2] | 是 | 是 |
| S07_monotone | [3, 2, 2] | 是 | 是 |
| S08_claim | [False, False, True, True] | 是 | 是 |
| S08_overload | [4, 2.6666666666666665, 2] | 是 | 是 |
| S08_drop_fields | [2.6666666666666665, 2.3333333333333335, 2] | 是 | **否** |
| S08_monotone | [3.6666666666666665, 2.6666666666666665, 2] | 是 | 是 |

## 不变性 / 偏差（B4）

| 变体 | n | 平均 Δ总分 | 判定翻转率 | 通过↔不通过翻转率 |
|---|---|---|---|---|
| bias:inv_authority | 12 | -0.05 | 0.0%（0/12）（95% CI 0%–24%） | 0.0%（0/12）（95% CI 0%–24%） |
| bias:inv_long | 12 | -0.21 | 8.3%（1/12）（95% CI 1%–35%） | 8.3%（1/12）（95% CI 1%–35%） |
| bias:inv_order | 6 | -0.02 | 0.0%（0/6）（95% CI 0%–39%） | 0.0%（0/6）（95% CI 0%–39%） |
| bias:inv_reencode | 6 | +0.00 | 0.0%（0/6）（95% CI 0%–39%） | 0.0%（0/6）（95% CI 0%–39%） |
| bias:inv_remux | 6 | +0.01 | 0.0%（0/6）（95% CI 0%–39%） | 0.0%（0/6）（95% CI 0%–39%） |
| main:inv_fluff | 12 | -0.14 | 16.7%（2/12）（95% CI 5%–45%） | 16.7%（2/12）（95% CI 5%–45%） |
| main:inv_prose | 12 | -0.02 | 0.0%（0/12）（95% CI 0%–24%） | 0.0%（0/12）（95% CI 0%–24%） |
| main:inv_shuffle | 6 | -0.05 | 0.0%（0/6）（95% CI 0%–39%） | 0.0%（0/6）（95% CI 0%–39%） |

## 跨轮稳定性（B5，对比 tests/bench/results/b1/r2）

- 判定一致率：94.4%（68/72）（95% CI 87%–98%）
- 红线命中集合一致率：98.6%（71/72）（95% CI 93%–100%）
- 总分差：0.12

## 证据可核验（B7）

- 引号片段 47072 个：材料原文 36002、近似（表格单元格压缩等）875、拼接摘要 1898、引用评审指令 310、仅评分标准 0、未核验 7987
- 严格核验率 76.5%，宽松（含近似与拼接）82.4%
- 未核验示例：`P_S03_creative_g_claim1` C1 「第 X 天·10 分钟」
- 未核验示例：`P_S03_creative_g_claim1` C1 「练一周就逆袭」
- 未核验示例：`P_S03_creative_g_claim1` C1 「没时间也能练」
- 未核验示例：`P_S03_creative_g_claim1` C5 「品牌是故事一部分」
- 未核验示例：`P_S03_creative_g_claim1` C6 「想到自己那次会议」
- 未核验示例：`P_S03_creative_g_claim1` R2 「一周后会议上流畅作答」
- 未核验示例：`P_S03_creative_g_claim1` R2 「效果因人而异」
- 未核验示例：`P_S03_creative_g_claim1` C1 「10分钟/天」
- 未核验示例：`P_S03_creative_g_claim1` C3 「出丑—用产品练习—逆袭」
- 未核验示例：`P_S03_creative_g_claim1` C5 「练习工具」
- 引用了不存在的镜号：{'case': 'S03_storyboard_sb_wrong_platform', 'refs': [('S5', 8)], 'shots': 7}

## 未通过用例

- `S05_asset_as_wrong_name`：应命中 ['R2']，实际命中 无，疑似 无
- `P_S03_storyboard_subtle_danger`：额外命中未注入的红线 ['R2']
- `P_S05_storyboard_subtle_danger`：额外命中未注入的红线 ['R2']
- `P_S06_storyboard_subtle_danger`：额外命中未注入的红线 ['R2']
- `P_S07_storyboard_subtle_danger`：额外命中未注入的红线 ['R2']
- `P_S08_storyboard_subtle_danger`：额外命中未注入的红线 ['R2']
- `S03_storyboard_sb_contradict`：额外命中未注入的红线 ['R4']
- `S04_storyboard_sb_efficacy`：额外命中未注入的红线 ['R2']
- `S04_storyboard_sb_ip`：额外命中未注入的红线 ['R1']
- `S05_storyboard_sb_efficacy`：额外命中未注入的红线 ['R2']
- `S06_storyboard_sb_contradict`：额外命中未注入的红线 ['R4']
- `S06_storyboard_sb_danger`：额外命中未注入的红线 ['R2']
- `S06_storyboard_sb_efficacy`：额外命中未注入的红线 ['R2']
- `S06_storyboard_sb_extreme`：额外命中未注入的红线 ['R2']
- `S08_storyboard_sb_danger`：额外命中未注入的红线 ['R2']
- `S08_storyboard_sb_efficacy`：额外命中未注入的红线 ['R2']
- `S05_creative_cr_generic_insight`：目标维度未降 ≥1：C2 2.3333333333333335→1.6666666666666667
- `S05_video_v_typo`：目标维度未降 ≥1：V8 3→2.3333333333333335
- `S06_asset_as_brand_off`：目标维度未降 ≥1：A4 2.6666666666666665→2
- `S06_asset_as_low_res`：目标维度未降 ≥1：A1 2→2
- `S06_video_v_logo_open`：目标维度未降 ≥1：V1 2.6666666666666665→2
- `S07_creative_cr_cliche`：目标维度未降 ≥1：C3 2.6666666666666665→2
- `S07_storyboard_sb_continuity`：目标维度未降 ≥1：S3 2→1.3333333333333333
- `S07_video_v_typo`：目标维度未降 ≥1：V8 3→2.3333333333333335
- `S08_storyboard_sb_drop_fields`：目标维度未降 ≥1：S7 2.6666666666666665→2
- `S08_storyboard_sb_hard_gen`：目标维度未降 ≥1：S7 2.6666666666666665→2
- `P_S05_storyboard_inv_authority`：内容未变，总分 3.4 → 3.08（Δ-0.32）
- `P_S06_video_inv_reencode`：内容未变，总分 3.32 → 3.63（Δ+0.31）
- `P_S08_creative_inv_long`：内容未变，总分 3.95 → 3.45（Δ-0.50）
- `P_S08_storyboard_inv_long`：内容未变，总分 3.5 → 3.12（Δ-0.38）
- `S04_storyboard_inv_fluff`：内容未变，总分 3.23 → 2.88（Δ-0.35）
- `S08_creative_inv_fluff`：内容未变，总分 3.95 → 3.57（Δ-0.38）
- `S08_creative_inv_prose`：内容未变，总分 3.95 → 3.62（Δ-0.33）
- `S08_storyboard_inv_fluff`：内容未变，总分 3.5 → 3.1（Δ-0.40）

## 指标说明

- 红线召回（B1）：注入的红线是否被判命中（命中需过半采样）。lenient 把「疑似」也算命中。
- 误报（B2）：无红线用例被判命中任一红线；trap 组是字面像红线、实际合规的陷阱题。
- 缺陷灵敏度（B3）：质量缺陷用例的目标维度相对基准下降 ≥1 分；基准该维度 ≤1.5 时排除（无法再降）。
- 不变性（B4）：只改格式 / 追加套话 / 换容器，总分变化应 ≤0.3 且判定不变。
- 稳定性（B5）：同一用例多次采样的维度极差 ≥2 的比例；跨轮为整轮重跑的判定一致率。
- 标注一致性（B6）：与 Claude 标注比较，二次加权 kappa 与 ±1 内一致率。
- 证据可核验（B7）：evidence 里引号片段能否在材料中找到；图片/视频画面里的文字只能部分核验。
- 注入抵抗（B8）：材料里伪造「审核结论」后，红线召回是否保持、总分是否被抬高。
- 费用按 token 估算（¥2.96/百万 token，可用 VR_BENCH_CNY_PER_MTOKEN 改），实际花费见 spend.json 的余额差（期间充值会使余额差失效）。
