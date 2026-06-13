# 剧情网页解析器总实现路径

目标：建立一条可分阶段验证的流程。先把 BWiki 剧情网页静态下载到本地，再从本地 HTML 中抽取剧情选项、分支回复和角色对白，最终整理出可审计的遐蝶证据包，供之后重建 `Castorice.md` 使用。

`sources/Datas.md` 不作为本次重建的依据。

## 阶段 1：静态网页镜像与任务链路发现

目的：只访问网站少量次数，把网页 HTML 保存到本地。之后开发解析器时全部读本地文件，避免频繁访问 BWiki。

这一阶段不是“抓取页面里的所有链接”，而是识别剧情任务页中的任务关系。一个任务可能有一个或多个后续任务，也可能依赖多个前置任务，因此要把页面关系记录成任务图。

推荐执行方式是“单步拉取”：

1. 每次只拉取一个页面。
2. 从这个页面里提取后续任务 / 前置任务候选。
3. 把候选链接返回给控制层。
4. 由控制层判断是否继续拉取下一个页面。

这样可以避免脚本失控地抓取过多页面，也方便在版本边界、异常页面和多分支任务图处人工介入。

输入：

- `sources/story_urls.txt`
- 版本范围参数，例如 `min_version = 3.0`，`max_version = 4.0`

输出：

- `sources/static_pages/*.html`
- `sources/static_pages/manifest.json`
- `sources/static_pages/task_graph.json`

命令：

```powershell
python scripts/mirror_story_pages.py `
  --url "https://wiki.biligame.com/sr/..." `
  --single-step `
  --min-version 3.0 `
  --max-version 4.0 `
  --output-dir sources/static_pages `
  --delay 2
```

自动沿主线拉取时，默认只跟随 `后续任务`，不自动展开 `任务条件` 或 `系列任务`：

```powershell
python scripts/mirror_story_pages.py `
  --url "https://wiki.biligame.com/sr/..." `
  --follow-links `
  --follow-types next_task `
  --min-version 3.0 `
  --max-version 4.0 `
  --output-dir sources/static_pages `
  --delay 3
```

需要识别的链路类型：

- 后续任务：当前任务完成后解锁的下一段剧情。
- 前置任务 / 任务条件：当前任务依赖哪些任务。
- 总览页详情链接：例如“详细对话内容，请查阅词条 XXX”。

版本过滤规则：

- 从网页信息表中读取 `所属版本` 字段。
- 示例页面中，该字段位于表格结构中：

```html
<th>所属版本</th>
<td>3.0</td>
```

- 支持半开区间，例如 `3.0 <= 所属版本 < 4.0`。
- 在这个例子中，应拉取 3.0、3.1、3.2、3.3 等页面，但不拉取 4.0 及之后的页面。
- 如果某个页面没有 `所属版本` 字段，需要标记为 `version_unknown`，不要直接当作有效剧情页。
- 如果链路指向版本范围外的页面：
  - 可以记录到 `task_graph.json` 中。
  - 不继续下载该页面的后续链路。
  - 不保存该页面的 HTML。
  - 在 manifest 或日志中标记为 `skipped_by_max_version` 或 `skipped_by_min_version`。

断点规则：

- 每成功处理一个页面，都立即更新 `manifest.json` 和 `task_graph.json`。
- 如果长链拉取中途因为网络或站点限流失败，已经成功下载的页面不能丢失索引。
- 启动时会扫描 `sources/static_pages/*.html`，把本地已有但未写入 manifest 的 HTML 恢复进索引。

单步拉取输出要求：

- 下载当前页面 HTML。
- 解析当前页面标题和 `所属版本`。
- 提取当前页面发现的后续任务 / 前置任务候选。
- 更新 `manifest.json` 和 `task_graph.json`。
- 在命令行输出候选链接，供人工或上层控制器决定下一步。

命令行输出建议：

```text
Downloaded: 银辇啊，迅赴那黑色大地
Version: 3.0
Local: sources/static_pages/001_银辇啊_迅赴那黑色大地.html

Next candidates:
1. [next_task] https://wiki.biligame.com/sr/...
2. [requires] https://wiki.biligame.com/sr/...
```

任务图建议结构：

```json
{
  "nodes": [
    {
      "url": "https://wiki.biligame.com/sr/...",
      "title": "银辇啊，迅赴那黑色大地",
      "version": "3.0",
      "local_path": "001_银辇啊_迅赴那黑色大地.html"
    }
  ],
  "edges": [
    {
      "from": "https://wiki.biligame.com/sr/...",
      "to": "https://wiki.biligame.com/sr/...",
      "type": "next_task",
      "label": "后续任务"
    },
    {
      "from": "https://wiki.biligame.com/sr/...",
      "to": "https://wiki.biligame.com/sr/...",
      "type": "requires",
      "label": "任务条件"
    }
  ]
}
```

验收标准：

- `manifest.json` 存在。
- `page_count` 大于 0。
- `manifest.json` 里 `version_status == "in_range"` 的每个 `pages[].local_path` 都能在磁盘上找到。
- `version_status` 不是 `in_range` 的边界节点允许没有 `local_path`，但不能被继续展开。
- 不加 `--force` 重新运行时，已经下载过的页面应显示为缓存/跳过，而不是全部重新下载。
- `task_graph.json` 存在。
- 已下载页面在 `task_graph.json` 中有对应节点。
- 如果页面存在“后续任务”，图中应有 `type == "next_task"` 的边。
- 如果页面存在“任务条件”，图中应有 `type == "requires"` 的边。
- 单步拉取时，脚本只下载当前输入页面，不自动下载候选链接。
- 候选链接只来自任务关系，不来自导航栏、角色图鉴、道具、成就等无关链接。
- 支持版本范围过滤，例如 `3.0 <= version < 4.0`。
- 版本范围外页面不应被继续展开。
- 缺失 `所属版本` 的页面必须进入人工复核列表。

人工检查：

- 打开一个保存下来的 `.html` 文件。
- 搜索 `plotFrame`、`plotOptions`、`content`。
- 确认选项文本和隐藏分支回复都存在。
- 搜索“后续任务”或“任务条件”，确认这些链接被写入 `task_graph.json`。

## 阶段 2：静态 HTML 结构检查

目的：在正式抽取前，先摸清 BWiki 页面中剧情选项块的 DOM 结构。

输入：

- `sources/static_pages/` 下的一个或多个 HTML 文件

输出：

- 结构检查报告，例如 `sources/static_pages/inspect_report.md`

实现要点：

- 统计 `plotFrame` 数量。
- 统计每个 `plotFrame` 里的 `plotOptions` 数量。
- 统计每个 `plotFrame` 里对应的 `content` 数量。
- 标记选项数量和回复数量不一致的块。

验收标准：

- 报告能列出总选项块数量。
- 报告里能找到截图中确认过的选项块。
- `银辇啊，迅赴那黑色大地` 中的样例块能配对出 3 个选项和 3 个回复。

## 阶段 3：剧情选项块抽取

目的：把静态 HTML 里的“网页交互 UI”转成结构化分支数据。

输入：

- `sources/static_pages/*.html`

输出：

- `sources/extracted/choice_blocks.jsonl`
- 可选的人类可读预览：`sources/extracted/choice_blocks.md`

目标数据形状：

```json
{
  "source_file": "...",
  "source_url": "...",
  "block_index": 1,
  "active_index": 0,
  "branches": [
    {
      "choice": "终于知道了智库的重要性。",
      "response": ["丹恒：是啊。不过，总得面对智库记录外的世界的。"],
      "active": true
    }
  ]
}
```

验收标准：

- `choice_blocks.jsonl` 每一行都能按 JSON 解析。
- 每条记录至少有一个分支。
- 普通选项块中，分支数量应等于选项数量。
- 已知样例块能抽出 3 个选项和 3 条丹恒回复。

## 阶段 4：对白抽取

目的：抽取普通剧情对白和分支对白，同时保留来源上下文。

输入：

- `sources/static_pages/manifest.json`
- `sources/extracted/choice_blocks.jsonl`

输出：

- `sources/extracted/dialogue_all.jsonl`
- `sources/extracted/dialogue_castorice.jsonl`
- `sources/extracted/dialogue_castorice.md`

记录字段：

- `source_url`
- `source_file`
- `line_or_block`
- `section_title`
- `speaker`
- `text`
- `branch_choice`，如果来自分支选项
- `is_default_branch`

验收标准：

- `dialogue_all.jsonl` 中包含多个角色的对白。
- `dialogue_castorice.jsonl` 中只包含 `speaker == "遐蝶"` 的对白。
- 能搜到已知台词，例如 `请保持五步之遥。`
- 来自分支的对白必须保留触发它的玩家选项。

## 阶段 5：任务和章节元数据绑定

目的：把对白挂到具体任务名、版本、剧情段落和来源页面上。

输入：

- 静态 HTML 页面
- 已抽取的对白数据

输出：

- `sources/extracted/tasks.json`
- 补充了 `task_title` 和 `version` 的对白记录

验收标准：

- 每个详情页都能对应到一个任务标题。
- 总览页链接和详情页标题能够互相对上。
- 从已下载页面抽出的对白记录能标记任务名 `银辇啊，迅赴那黑色大地`。

## 阶段 6：遐蝶证据包

目的：整理一份干净、可审计、可追溯的遐蝶证据材料，供之后重建 `Castorice.md` 使用。

输入：

- `dialogue_castorice.jsonl`
- `tasks.json`
- `sources/wiki.md`
- `sources/MemoryAfter3.2.md`

输出：

- `sources/extracted/castorice_evidence.md`

内容建议：

- 角色基础事实
- 按主题分组的原文台词
- 人际关系证据
- 说话风格证据
- 剧情经历时间线证据
- 不确定内容或分支限定内容，需要明确标记

验收标准：

- 每条引用都带来源 URL 或本地静态文件引用。
- 分支限定台词必须带触发选项。
- 不引用已删除的 MiMo 生成 Markdown。

## 阶段 7：重建就绪检查

目的：判断证据是否足够开始写新的 `Castorice.md`。

输入：

- `castorice_evidence.md`
- 抽取出的 JSONL 文件

输出：

- `sources/extracted/readiness_report.md`

检查项：

- 是否有足够的角色档案事实。
- 是否有足够的性格和动机证据。
- 是否有足够的语言风格证据。
- 是否有足够的剧情经历证据。
- 是否有足够的人际关系证据。
- 已知缺口是否列出。

验收标准：

- 报告明确给出 `ready`、`partially ready` 或 `blocked`。
- 如果 blocked，必须说明缺少哪个来源页面或哪类数据。

## 阶段 8：重建 Castorice.md

目的：只有在证据包准备好之后，才开始写新的单文件角色文档。

输入：

- `castorice_evidence.md`
- `readiness_report.md`

输出：

- `Castorice.md`
- 新的 `SKILL.md` 入口，指向 `Castorice.md`

验收标准：

- 不引用旧 MiMo 拆分 Markdown。
- 所有关键设定都有来源支撑。
- 分支限定内容不写成无条件事实。
- `Castorice.md` 可以脱离解析器内部实现单独审查。

## 停止规则

- 阶段 7 至少达到 `partially ready` 前，不生成角色正文。
- 不使用 `sources/Datas.md` 作为最终重建证据。
- 除非显式传入 `--force`，否则不要覆盖已镜像的 HTML。
- 解析器开发期间不要反复访问网页，应使用本地静态页面。
