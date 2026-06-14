import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const defaultSkillRoot = path.resolve(scriptDir, "..");

const categoryPatterns = [
  {
    heading: "世界观要点",
    re: /翁法罗斯|轮回|火种|泰坦|半神|再创世|权杖|铁墓|毁灭|负世|岁月|记忆|忘却|流光忆庭|神权|命途|冥界|冥河|死亡|塞纳托斯|玻吕|浮黎|博识尊/u,
  },
  {
    heading: "关系变化",
    re: /伙伴|同伴|朋友|信任|保护|牺牲|告别|重逢|拥抱|体温|愿望|承诺|谢谢|抱歉|对不起|一起|同行|开拓者|丹恒|三月七|长夜月|昔涟|白厄|遐蝶|阿格莱雅|刻律德菈|海瑟音|来古士|赞达尔/u,
  },
  {
    heading: "遐蝶 roleplay 相关信息",
    re: /遐蝶|死亡|冥河|冥界|塞纳托斯|玻吕|入殓|哀地里亚|奥赫玛|阿格莱雅|拥抱|体温|安提灵|缇安|缇宝|万敌|白厄|花海|灵魂/u,
  },
  {
    heading: "易错点/待复核点",
    re: /不是|并非|不复存在|真相|误会|混淆|欺骗|篡改|忘却|无法|只有|敌人|代价|牺牲|我不是|她不是|这件事，从来没有发生过/u,
  },
];

export async function rebuildStorySummaries(skillRoot = defaultSkillRoot) {
  const storyDir = path.join(skillRoot, "sources", "extracted", "story_pages");
  const summaryDir = path.join(storyDir, "summaries");
  await fs.mkdir(summaryDir, { recursive: true });

  const oldEntries = await fs.readdir(summaryDir, { withFileTypes: true });
  await Promise.all(
    oldEntries
      .filter((entry) => entry.isFile() && entry.name.endsWith(".md"))
      .map((entry) => fs.rm(path.join(summaryDir, entry.name), { force: true })),
  );

  const entries = await fs.readdir(storyDir, { withFileTypes: true });
  const storyFiles = entries
    .filter((entry) => entry.isFile() && entry.name.endsWith(".md"))
    .map((entry) => path.join(storyDir, entry.name))
    .sort((a, b) => path.basename(a).localeCompare(path.basename(b), "zh-Hans-CN"));

  const indexRows = [
    "# 剧情摘要索引",
    "",
    "> 自动生成自 `sources/extracted/story_pages/*.md`。本目录仅作导航/审计层，最终事实必须回溯到原始剧情文件。",
    "",
    "| 序号 | 版本 | 章节 | 摘要 | 关键角色 |",
    "| --- | --- | --- | --- | --- |",
  ];

  for (const filePath of storyFiles) {
    const text = await fs.readFile(filePath, "utf8");
    const lines = text.split(/\r?\n/);
    const title = getTitle(lines);
    const version = getVersion(lines);
    const sourcePath = getSourcePath(lines);
    const relativePath = toRepoPath(path.relative(skillRoot, filePath));
    const speakerStats = getSpeakerStats(lines);
    const headings = getSectionHeadings(lines);
    const choiceCount = lines.filter((line) => /^>\s*选项组\s+\d+/u.test(line)).length;
    const dialogueCount = lines.filter((line) => /^\s*-\s+\*\*.+?\*\*：/u.test(line)).length;

    const baseName = path.basename(filePath, ".md");
    const summaryName = `${baseName}.summary.md`;
    const summaryPath = path.join(summaryDir, summaryName);
    const summaryRelPath = toRepoPath(path.relative(skillRoot, summaryPath));

    const parts = [
      `# ${title}`,
      "",
      "> 自动生成自原始剧情 md。此文件只作导航/审计层，不作为最终事实依据；正式结论必须回到原文核对。",
      "",
      "## 基本信息",
      "",
      `- 原始文件：\`${relativePath}\``,
      `- 原始静态页：\`${sourcePath}\``,
      `- 所属版本：${version}`,
      `- 章节名：${title}`,
      `- 对话行数：${dialogueCount}`,
      `- 选项组数：${choiceCount}`,
      "",
      "## 关键角色",
      "",
      ...(speakerStats.length
        ? speakerStats.map(({ name, count }) => `- ${name}：${count} 行`)
        : ["- 未自动识别到对话角色；需要人工阅读原文。"]),
      "",
      "## 章节结构索引",
      "",
      ...(headings.length ? headings : ["- 未自动识别到章节结构。"]),
      "",
    ];

    for (const { heading, re } of categoryPatterns) {
      const anchors = getAnchors(lines, re, 10);
      parts.push(`## ${heading}`, "");
      parts.push(
        ...(anchors.length
          ? anchors
          : ["- 未自动抽取到明显锚点；需要人工阅读原文确认。"]),
      );
      parts.push("");
    }

    parts.push(
      "## 证据锚点",
      "",
      `- 本摘要中 \`L数字\` 均指向原始文件 \`${relativePath}\` 的行号。`,
      "- 需要写入 `worldview.md`、`relations.md`、`memory.md`、`canon_memory.md` 的结论，必须回到上述原始文件核对。",
      "",
    );

    await fs.writeFile(summaryPath, `${parts.join("\n").trimEnd()}\n`, "utf8");

    const keySpeakers = speakerStats.length
      ? speakerStats.slice(0, 5).map(({ name }) => name).join("、")
      : "未识别";
    indexRows.push(
      `| ${baseName.slice(0, 3)} | ${version} | ${title} | [\`${summaryName}\`](${summaryName}) | ${keySpeakers} |`,
    );
  }

  const indexPath = path.join(summaryDir, "_index.md");
  await fs.writeFile(indexPath, `${indexRows.join("\n").trimEnd()}\n`, "utf8");
  return { count: storyFiles.length, summaryDir: toRepoPath(path.relative(skillRoot, summaryDir)) };
}

function toRepoPath(value) {
  return value.split(path.sep).join("/");
}

function getTitle(lines) {
  for (const line of lines) {
    const match = line.match(/^#\s+(.+?)\s*$/u);
    if (match) return match[1].trim();
  }
  return "未识别标题";
}

function getVersion(lines) {
  for (const line of lines) {
    const match = line.match(/^\s*-\s*Version:\s*(.+?)\s*$/u);
    if (match) return match[1].trim();
  }
  return "unknown";
}

function getSourcePath(lines) {
  for (const line of lines) {
    const match = line.match(/^\s*-\s*Source:\s*(.+?)\s*$/u);
    if (match) return match[1].trim();
  }
  return "未记录";
}

function getSpeakerStats(lines) {
  const counts = new Map();
  const excluded = new Set(["旁白", "系统", "选项", "奖励", "获得物品"]);
  for (const line of lines) {
    const match = line.match(/^\s*-\s+\*\*(.+?)\*\*：/u);
    if (!match) continue;
    const name = match[1].trim();
    if (excluded.has(name)) continue;
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, "zh-Hans-CN"))
    .slice(0, 12);
}

function getSectionHeadings(lines) {
  const items = [];
  for (let i = 0; i < lines.length; i += 1) {
    const match = lines[i].match(/^(#{2,4})\s+(.+?)\s*$/u);
    if (!match) continue;
    const title = match[2].trim();
    if (title === "剧情内容") continue;
    items.push(`- L${i + 1}: H${match[1].length} ${title}`);
    if (items.length >= 16) break;
  }
  return items;
}

function getAnchors(lines, re, limit) {
  const items = [];
  for (let i = 0; i < lines.length; i += 1) {
    if (!re.test(lines[i])) continue;
    const snippet = limitSnippet(lines[i]);
    if (!snippet) continue;
    items.push(`- L${i + 1}: ${snippet}`);
    if (items.length >= limit) break;
  }
  return items;
}

function limitSnippet(text) {
  const clean = text.replace(/\s+/gu, " ").trim();
  if (!clean) return "";
  return clean.length > 130 ? `${clean.slice(0, 130)}...` : clean;
}
