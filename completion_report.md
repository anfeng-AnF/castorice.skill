# 重建完成度报告

本报告记录本轮基于原始剧情文本重建遐蝶 roleplay skill 的完成范围、验证结果与剩余风险。它不是角色 canon 来源。

## 完成范围

- 已确认仓库存在提交后，清理 `sources/extracted/story_pages/summaries/` 中旧 Claude 归纳文件，未删除 `sources/extracted/story_pages/`、`sources/extracted/profile_pages/`、`sources/extracted/supplemental_pages/`、`sources/extracted/coverage_summary.md`、`sources/extracted/plot_mismatch_review.md` 等原始或校对资料。
- 已新增 `scripts/rebuild_story_summaries.mjs`，从 `sources/extracted/story_pages/*.md` 原文重建 64 个章节 summary 和 `sources/extracted/story_pages/summaries/_index.md`。
- 新 summaries 明确只作为导航/审计层，不作为最终事实依据；旧 Claude summaries 不再作为事实来源或候选记忆来源。
- 已扩写 `worldview.md`：覆盖翁法罗斯轮回、火种、泰坦/半神、再创世、记忆/忘却、流光忆庭、铁墓/毁灭、冥界/死亡权柄，并加入阶段 1 测试题。
- 已重写 `relations.md`：覆盖遐蝶与开拓者、阿格莱雅、白厄、万敌、缇安/缇宝、昔涟、玻吕茜亚/塞纳托斯、玻吕刻斯，以及三月七/长夜月、海瑟音/刻律德菈、白厄/来古士、昔涟/轮回等重要关系。
- 已将视角认知层目录化：`perspective.md` 作为总入口，`perspectives/*.md` 按人物/关系拆分直接知道、可能通过转述知道、默认不应知道，防止全知旁白化并降低维护成本。
- 已更新 `Castorice.md`、`memory.md`、`canon_memory.md`、`conflicts.md`、`source_index.md`、`SKILL.md`、`manifest.json`，接入世界观、关系网、视角边界、高频误写与验证文件。
- 已新增 `validation_questions.md`：包含 20 个设定测试问题，每题有简短标准答案和证据路径。

## 覆盖结论

- 阶段 0：清理污染源与重建 summaries，已完成。
- 阶段 1：世界观底座，已完成。
- 阶段 2：关系网，已完成。
- 阶段 2.5：遐蝶视角人物认知层，已完成并拆分为入口文件与 12 个人物/关系文件。
- 阶段 3：遐蝶个人故事连续性，已通过 `memory.md`、`canon_memory.md`、`perspective.md` 与 `perspectives/*.md` 补齐并接入。
- 阶段 4：高频易错点，已通过 `canon_memory.md`、`conflicts.md`、`validation_questions.md` 固化。
- 阶段 5：测试问题与基础校验，已完成。

## 已验证

- `manifest.json` 可用 PowerShell `ConvertFrom-Json` 解析。
- `manifest.json` 的 `dimensions` 已包含 `perspective.md`、`perspectives/*.md`、`validation_questions.md` 与 `completion_report.md`。
- `worldview.md`、`relations.md`、`perspective.md`、`perspectives/*.md`、`validation_questions.md` 中的证据行号已检查，均能解析到现有文件。
- `Castorice.md`、`memory.md`、`canon_memory.md`、`conflicts.md`、`worldview.md`、`relations.md`、`perspective.md`、`perspectives/*.md`、`source_index.md`、`SKILL.md` 未发现绝对路径。
- `git diff --check -- .` 通过，仅有 Windows 换行提示。

## 待人工复核点

- `perspectives/herta-blackswan-sunday.md` 与 `perspectives/lycurgus-zandar.md` 中外部角色的“遐蝶可能通过转述知道”边界是保守策略；若后续发现遐蝶确有更直接交互，可补证据。
- `validation_questions.md` 目前覆盖 20 个高频问题，偏设定正确性；若要测试语气质量，可再增加多轮 roleplay 样例。
- `summaries/` 由脚本自动抽取导航要点，不作为事实来源；如果未来用它定位证据，应继续回原始剧情页复核。

## 剩余风险

- 大量剧情事实仍来自本地解析的静态网页文本；动态选项内容虽已做过人工补录与校对，但未来若官方页面变更，需要重新抓取与复核。
- 角色语气质量还需要实际对话测试验证，尤其是轻松后日谈与严肃冥界场景之间的切换。
- 目前没有自动化 roleplay 评测器；`validation_questions.md` 是人工或半自动验收题库。
