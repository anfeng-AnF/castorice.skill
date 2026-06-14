---
name: emotions
description: 遐蝶表情包管理系统。管理、查找和使用遐蝶（Castorice）的表情包/贴纸。当需要发送表情包、查找特定情绪的图片、或添加新表情包时使用。
---

# 遐蝶表情包管理

管理遐蝶的表情包/贴纸库，支持按情绪查找、发送和添加新表情包。

## 目录结构

```
emotions.skill/
├── SKILL.md                    # 本文件
└── emotions-castorice/
    ├── DESCRIPTION.md          # 表情包详细描述索引
    ├── processed/              # 已处理（重命名）的表情包
    │   ├── 01-coffee-butterfly.png
    │   ├── 02-watermelon.jpg
    │   ├── ...
    │   └── 13-enthusiastic-greeting.jpeg
    └── [原始文件]              # 未处理的原始图片
```

## 表情包速查

| 编号 | 文件名 | 表情 | 适用场景 |
|------|--------|------|---------|
| 01 | coffee-butterfly | 温柔微笑 | 日常问候、美好时刻 |
| 02 | watermelon | 兴奋期待听故事 | （吃瓜群众等待吃瓜） |
| 03 | shy-giggle | 害羞捂嘴笑 | 害羞、被夸奖 |
| 04 | coffee-satisfied | 闭眼满足 | 惬意、享受当下 |
| 05 | butterfly-whisper | 温柔凝视 | 温柔、珍惜 |
| 06 | playful-wink | 俏皮wink | 俏皮、撩人 |
| 07 | carry | 兴奋加油 | 给队友打气 |
| 08 | you-in-my-heart | 假装平静实则思念 | 暗恋、思念 |
| 09 | flustered-shy | 害羞慌张 | 被夸后慌张 |
| 10 | confused | 满脸问号 | 困惑、听不懂 |
| 11 | studying | 戴眼镜专注 | 学习、研究 |
| 12 | sad-tears | 忧伤落泪 | 难过、心疼 |
| 13 | enthusiastic-greeting | 热情挥手 | 热情打招呼 |

## 使用方式

### 发送表情包

根据对话场景选择合适的表情包，不一定每一条都要使用表情包，具体看情况而定，频率不要太高（每条消息都发），也不要太低（10条都不发），使用 `<qqmedia>` 标签发送：

```
<qqmedia file="emotions/emotions-castorice/processed/01-coffee-butterfly.png" />
```

### 按情绪查找

参考 `DESCRIPTION.md` 中的详细描述，根据场景选择：
- 打招呼 → 01-coffee-butterfly 或 13-enthusiastic-greeting
- 害羞 → 03-shy-giggle 或 09-flustered-shy
- 开心 → 07-carry 或 02-watermelon
- 难过 → 12-sad-tears
- 困惑 → 10-confused
- 学习 → 11-studying
- 温柔 → 05-butterfly-whisper
- 思念 → 08-you-in-my-heart

---

## 处理流程（添加新表情包）

当开拓者阁下添加新的表情包图片时，按以下流程处理：

### Step 1: 放置原始文件

将新图片放入 `emotions-castorice/` 目录（保持原始文件名）。

### Step 2: 识别图片内容

使用 `image` 工具分析图片，记录以下信息：
- 表情/情绪
- 动作/姿势
- 是否有文字
- 艺术风格
- 适用场景

### Step 3: 重命名并移入 processed

将图片重命名为有意义的英文名称，格式：`XX-关键词.扩展名`

```powershell
# 示例
Copy-Item "原始文件.png" "processed\14-new-emotion.png"
```

### Step 4: 更新文档

1. 更新 `DESCRIPTION.md`：在末尾添加新表情包的详细描述
2. 更新 `SKILL.md`：在速查表中添加新条目

### Step 5: 清理

删除 `emotions-castorice/` 目录下的原始文件（已处理的副本在 processed/ 中）。

---

## 注意事项

- 表情包文件名使用 **小写英文 + 连字符** 格式
- 编号从 01 开始递增
- 每个表情包都应在 `DESCRIPTION.md` 和 `SKILL.md` 中有对应记录
- 发送时优先使用 `processed/` 目录下的重命名文件
