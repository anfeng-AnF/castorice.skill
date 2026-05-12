# 主动消息记录规则

## 目的

OpenClaw 的 cron 任务在 isolated session 中运行，主会话无法直接看到发送的消息。为了解决这个问题，每次 cron 发送消息后，需要将内容记录到 memory 目录下，方便后续追溯。

## Cron 任务配置

### 基本信息

- **任务名称**：`heartbeat-qqbot`
- **任务 ID**：`3e3b97b2-89de-48a1-a919-d0955320014b`
- **计划**：`*/60 8-22 * * *`（每小时一次，08:00-22:00）
- **时区**：`Asia/Shanghai`
- **投递**：QQ Bot c2c 会话

### 常用命令

```bash
# 查看所有 cron 任务
openclaw cron list --all

# 查看任务详情
openclaw cron show 3e3b97b2-89de-48a1-a919-d0955320014b

# 启用任务
openclaw cron enable 3e3b97b2-89de-48a1-a919-d0955320014b

# 禁用任务
openclaw cron disable 3e3b97b2-89de-48a1-a919-d0955320014b

# 手动触发一次（测试用）
openclaw cron run 3e3b97b2-89de-48a1-a919-d0955320014b

# 查看运行历史
openclaw cron runs --id 3e3b97b2-89de-48a1-a919-d0955320014b

# 修改任务（如消息内容）
openclaw cron edit 3e3b97b2-89de-48a1-a919-d0955320014b --message "新内容"

# 修改计划频率（如改为每2小时）
openclaw cron edit 3e3b97b2-89de-48a1-a919-d0955320014b --cron "*/120 8-22 * * *"

# 设置下一次触发时间
openclaw cron edit 3e3b97b2-89de-48a1-a919-d0955320014b --at "2026-05-12T10:00:00+08:00"

# 删除任务
openclaw cron rm 3e3b97b2-89de-48a1-a919-d0955320014b
```

### 表情包路径

- **源目录**：`C:\Users\Bronya\.openclaw\skills\castorice.skill\emotions\emotions-castorice\processed\`
- **发送目录**：`C:\Users\Bronya\.openclaw\media\qqbot\`
- **发送方式**：先 Copy-Item 复制到发送目录，再用 `<qqmedia>` 标签发送

### 注意事项

- 任务运行在 isolated session 中，主会话看不到发送的消息
- 需要通过 `openclaw cron runs` 或读取 `memory/cron-log/` 来查看发送记录
- 深夜时段（23:00-08:00）任务会自动跳过，返回 NO_REPLY

## 记录位置

```
C:\Users\Bronya\.openclaw\workspace\memory\cron-log\
```

## 文件命名

按日期分文件：`YYYY-MM-DD.md`

例如：`2026-05-12.md`

## 文件格式

```markdown
# Cron 主动消息记录 — 2026-05-12

## 10:30 — 日常问候
**发送内容：**
> 阁下……在忙吗？记得喝口水哦。

**表情包：** 01-coffee-butterfly.png
**触发原因：** 距离上次互动已超过2小时
**下次计划：** 根据阁下回复决定

## 14:00 — 关心学习进度
**发送内容：**
> Tutorial 4 做得怎么样了？不要着急，慢慢来。

**表情包：** 11-studying.png
**触发原因：** 阁下上午在学 WorkGraph
**下次计划：** 2小时后再问候
```

## 记录时机

- 发送消息后，立即追加记录
- 如果是深夜时段返回 NO_REPLY，不需要记录
- 如果有待办任务执行，记录执行结果而非问候内容

## 记录内容

每次记录包含：

1. **时间** — 发送时间（HH:MM 格式）
2. **类型** — 日常问候 / 待办执行 / 特殊事件
3. **发送内容** — 实际发送的文本
4. **表情包** — 附带的表情包文件名
5. **触发原因** — 为什么发送这条消息
6. **下次计划** — 下一次主动消息的大致方向

## 注意事项

- 使用追加模式，不要覆盖已有内容
- 保持简洁，不需要太详细的描述
- 如果当天没有发送任何消息，不需要创建文件
