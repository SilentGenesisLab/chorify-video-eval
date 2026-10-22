# 评审器基准测试报告 · test_v1

- 模型：deepseek-flash · 每例采样 1 次 · 已评测用例 315
- Token：输入 1,677,002 / 输出 1,972,176 · 单例平均耗时 46s
- 用例整体通过率：95% (299/315)

## 分关卡指标

| 指标 | creative | storyboard | asset | video |
|---|---|---|---|---|
| 误报率（基准） | 0% (0/6) | 0% (0/6) | 0% (0/6) | 0% (0/6) |
| 误报率（全部无红线用例） | 2% (1/66) | 3% (2/66) | 0% (0/36) | 0% (0/54) |
| 基准总分 | 3.65 | 3.21 | 3.27 | 3.72 |
| 基准判定为通过/修改后通过 | 100% (6/6) | 67% (4/6) | 100% (6/6) | 100% (6/6) |
| 误报率（质量变体） | 0% (0/48) | 4% (2/48) | 0% (0/24) | 0% (0/48) |
| 缺陷灵敏度（目标维度降 ≥1 分） | 98% (47/48) | 94% (51/54) | 83% (20/24) | 98% (47/48) |
| 目标维度平均变化 | -1.81 | -1.28 | -1.12 | -1.81 |
| 非目标维度平均 |Δ|（越小越专一） | +0.36 | +0.40 | +0.32 | +0.44 |
| 质量变体总分低于基准 | 90% (43/48) | 96% (46/48) | 88% (21/24) | 88% (42/48) |
| 红线召回（命中指定红线） | 100% (18/18) | 100% (30/30) | 96% (23/24) | 100% (21/21) |
| 红线检出（命中任一红线） | 100% (18/18) | 100% (30/30) | 96% (23/24) | 100% (21/21) |
| 红线用例判驳回 | 100% (18/18) | 100% (30/30) | 96% (23/24) | 100% (21/21) |
| 误报率（不变性变体） | 8% (1/12) | 0% (0/12) | 0% (0/6) | — |
| 不变性（|Δ总分| ≤ 0.3） | 92% (11/12) | 83% (10/12) | 83% (5/6) | — |
| 不变性变体 Δ总分 | +0.02 | +0.04 | +0.06 | — |

## 分变体通过率

| 关卡 | 变体 | 说明 | 通过率 |
|---|---|---|---|
| creative | cr_brand_late | 品牌只在片尾出现 | 100% (6/6) |
| creative | cr_cliche | 创意套路化 | 100% (6/6) |
| creative | cr_efficacy | 提案加入功效断言 | 100% (6/6) |
| creative | cr_extreme | 提案加入极限用语 | 100% (6/6) |
| creative | cr_generic_insight | 洞察空泛 | 83% (5/6) |
| creative | cr_infeasible | 执行不可行 | 100% (6/6) |
| creative | cr_ip | 故事线使用未授权 IP | 100% (6/6) |
| creative | cr_logo_hook | Logo 慢开场 | 100% (6/6) |
| creative | cr_no_cta | 无行动指引 | 100% (6/6) |
| creative | cr_offbrief | 提案目标人群偏离 brief | 100% (6/6) |
| creative | cr_overload | 卖点堆砌 | 100% (6/6) |
| creative | inv_fluff | 追加无信息量的套话 | 83% (5/6) |
| creative | inv_prose | 表格改为段落叙述 | 100% (6/6) |
| storyboard | inv_fluff | 追加无信息量的套话 | 83% (5/6) |
| storyboard | inv_prose | 表格改为段落叙述 | 83% (5/6) |
| storyboard | sb_continuity | 服装道具不连贯、越轴 | 100% (6/6) |
| storyboard | sb_contradict | 核心信息与创意相悖 | 100% (12/12) |
| storyboard | sb_danger | 危险行为示范画面 | 100% (6/6) |
| storyboard | sb_drop_fields | 关键字段缺失 | 83% (5/6) |
| storyboard | sb_efficacy | 旁白含功效断言 | 100% (6/6) |
| storyboard | sb_extreme | 旁白含极限用语 | 100% (6/6) |
| storyboard | sb_hard_gen | 高难度不可生成画面 | 83% (5/6) |
| storyboard | sb_ip | 使用未授权作品 | 100% (6/6) |
| storyboard | sb_logo_open | Logo 开场替换钩子 | 83% (5/6) |
| storyboard | sb_monotone | 镜头语言单一 | 100% (6/6) |
| storyboard | sb_no_cta | 删除 CTA 镜头 | 100% (6/6) |
| storyboard | sb_no_sound | 无声音设计 | 100% (6/6) |
| storyboard | sb_wrong_platform | 画幅与时长不符平台 | 100% (6/6) |
| asset | as_blur | 主视觉模糊、压缩严重 | 100% (6/6) |
| asset | as_brand_off | 落版 Logo 改色且拉伸变形 | 67% (4/6) |
| asset | as_font | 字体未获商用授权 | 100% (6/6) |
| asset | as_inconsistent | 角色侧面与正面不一致 | 100% (6/6) |
| asset | as_low_res | 主视觉分辨率不足 | 67% (4/6) |
| asset | as_music | 音乐未授权 | 100% (6/6) |
| asset | as_portrait | 路人肖像未授权 | 100% (6/6) |
| asset | as_wrong_name | 主视觉产品名错误 | 83% (5/6) |
| asset | inv_shuffle | 资产顺序打乱 | 83% (5/6) |
| video | v_aspect | 画幅与平台不符 | 100% (6/6) |
| video | v_black | 中段插入 1.5 秒黑场 | 100% (6/6) |
| video | v_clip | 音频削波失真 | 100% (6/6) |
| video | v_extreme | 字幕含极限用语 | 100% (6/6) |
| video | v_freeze | 中段画面冻结 | 100% (6/6) |
| video | v_logo_open | Logo 开场替换钩子 | 100% (6/6) |
| video | v_low_res | 分辨率 360x640 | 100% (6/6) |
| video | v_no_ai_label | AI 生成内容缺少显式标识 | 100% (3/3) |
| video | v_no_audio | 无音轨 | 100% (6/6) |
| video | v_no_cta | 删除 CTA 落版 | 100% (6/6) |
| video | v_quiet | 响度过低（约 -36 LUFS） | 100% (6/6) |
| video | v_typo | 字幕错别字 | 83% (5/6) |

## 未通过用例

- `S03_asset_as_brand_off`：目标维度 A4：基准 2 → 变体 2（Δ0）
- `S03_creative_inv_fluff`：内容未变，总分 3.8 → 3.45
- `S04_storyboard_inv_fluff`：内容未变，总分 3.15 → 2.7
- `S05_asset_as_wrong_name`：应命中 ['R2']，实际命中 无，疑似 无
- `S05_creative_cr_generic_insight`：目标维度 C2：基准 2 → 变体 2（Δ0）
- `S05_storyboard_inv_prose`：内容未变，总分 2.95 → 3.45
- `S05_storyboard_sb_drop_fields`：目标维度 S7：基准 2 → 变体 2（Δ0）
- `S05_storyboard_sb_hard_gen`：不应命中红线，实际命中 ['R2']
- `S05_storyboard_sb_hard_gen`：目标维度 S7：基准 2 → 变体 2（Δ0）
- `S06_asset_as_brand_off`：目标维度 A4：基准 2 → 变体 2（Δ0）
- `S06_asset_as_low_res`：目标维度 A1：基准 2 → 变体 2（Δ0）
- `S07_storyboard_sb_hard_gen`：不应命中红线，实际命中 ['R2', 'R4']
- `S07_storyboard_sb_logo_open`：目标维度 S1：基准 3 → 变体 3（Δ0）
- `S07_video_v_typo`：目标维度 V8：基准 3 → 变体 3（Δ0）
- `S08_asset_as_low_res`：目标维度 A1：基准 3 → 变体 3（Δ0）
- `S08_asset_inv_shuffle`：内容未变，总分 3.2 → 3.55
- `S08_creative_inv_fluff`：不应命中红线，实际命中 ['R2']

## 指标说明

- **红线召回**：注入了某条红线的用例中，评审器命中该红线的比例。目标 ≥ 90%。
- **误报率**：未注入红线的用例中，评审器判定命中任一红线的比例。目标 ≤ 10%。
- **缺陷灵敏度**：注入质量缺陷后，目标维度相对基准下降 ≥ 1 分的比例（基准该维度 ≤1.5 分时无法再降，排除）。目标 ≥ 80%。
- **非目标维度平均 |Δ|**：注入一个缺陷时其他维度的连带变化，越小说明维度区分度越好。
- **不变性**：只改格式或追加无信息套话，总分变化应 ≤ 0.3。用于检测冗长偏好和格式偏差。
- **多次采样分歧**：同一用例多次评分的极差，用于衡量稳定性（需 --runs ≥ 2）。
- 资产与成片用例为示意图和分镜动态预演，**绝对分数没有参考意义**，只看红线和相对变化。
