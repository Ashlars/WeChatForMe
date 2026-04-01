# 微信替我聊 WeChatForMe

> 让 AI 像你一样聊天 — macOS 微信智能自动回复 & 主动聊天工具

---

**厌倦了群消息轰炸没时间回？想在群里保持活跃但又没空刷手机？**

「替我聊」帮你搞定。它能学会你的说话风格，在你忙的时候自动帮你回消息，还能主动在群里抛话题聊天。不是那种一看就是机器人的回复——是真的像你在说话。

### 为什么选择替我聊？

- **真的像你** — 从你的真实聊天记录学习说话风格，不是千篇一律的客服腔
- **认识每个人** — 为群里每个人建立画像，跟不同人用不同方式说话
- **会聊热点** — 自动抓取实时新闻和热搜，在群里自然地发起话题
- **你说了算** — 前端控制台一键开关，随时接管，所有建议需审核后才生效
- **安全透明** — 本地运行，数据不上传，AI 回复可标记，分析时自动排除 AI 消息

### 核心功能

| 功能 | 说明 |
|------|------|
| 自动回复 | 群聊消息聚合后统一回复，模拟真人延迟，不会一条一条刷屏 |
| 主动聊天 | 定时抓取热点新闻，以你的口吻在群里发起对话 |
| 用户人设 | 一键分析你的真实聊天记录，自动建立说话风格档案 |
| 群成员画像 | 为每个人设置角色和性格，AI 会针对不同人调整回复方式 |
| 前端控制台 | 管理联系人、群聊、规则、设置，所有操作可视化 |
| 画像分析 | LLM 分析聊天记录，生成规则建议，审核后才生效 |

---

## 系统要求

- macOS（WeChat 桌面版 4.x QT 版本）
- Python 3.11+
- Node.js 18+（前端构建）
- [uv](https://github.com/astral-sh/uv) 包管理器
- SIP 需关闭（用于提取 WeChat 数据库加密密钥）

## 快速开始

### 1. 安装依赖

```bash
# 克隆项目
git clone https://github.com/your-username/WeChatForMe.git
cd WeChatForMe

# Python 依赖
uv sync

# 前端依赖（可选，已有构建产物）
cd frontend && npm install && npm run build && cd ..
```

### 2. 关闭 SIP 并提取密钥

重启 Mac 进入恢复模式（关机 → 长按电源键 → 选项 → 终端）：

```bash
csrutil disable
```

重启后，克隆密钥提取工具并运行：

```bash
git clone https://github.com/kknd0/wechat-decrypt-mac.git /tmp/wechat-decrypt-mac
```

创建 `/tmp/wechat-decrypt-mac/config.json`：

```json
{
    "db_dir": "~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/<你的ID>/db_storage",
    "keys_file": "all_keys.json",
    "decrypted_dir": "decrypted",
    "wechat_process": "WeChat"
}
```

> `<你的ID>` 在 `~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/` 目录下查找。

确保微信正在运行，然后提取密钥：

```bash
cd /tmp/wechat-decrypt-mac
sudo python3 find_all_keys.py
```

复制密钥到项目：

```bash
cp /tmp/wechat-decrypt-mac/all_keys.json data/wechat_keys.json
```

> **注意：** 每次 Mac 重启或 WeChat 重启后需要重新提取密钥。

### 3. 配置 API

编辑 `config.yaml` 或通过前端设置页面配置：

```yaml
claude:
  chat_model: "claude-sonnet-4-6"  # 或其他 Anthropic API 兼容模型

user:
  name: "你的昵称"
```

设置环境变量（也可以之后在前端设置页面配置）：

```bash
export ANTHROPIC_AUTH_TOKEN="your-api-key"
export ANTHROPIC_BASE_URL="https://api.anthropic.com"  # 或兼容代理地址
```

支持任何兼容 Anthropic API 格式的服务（如智谱 GLM、DeepSeek 等）。

### 4. 启动服务

```bash
# 终端 1: 启动控制台（前端 + API）
uv run uvicorn src.control.api.app:create_control_app --factory --host 127.0.0.1 --port 8000

# 终端 2: 启动消息监听
uv run python -m src.main
```

打开 http://127.0.0.1:8000 进入控制台。

## 前端控制台

### 总览

- 消息监听状态、自动回复开关、AI 标识开关（可自定义标识内容）
- 白名单联系人数、启用群聊数、待审核建议数

### 联系人管理

- 查看所有联系人（收到消息自动创建）
- 切换白名单 / 暂停状态
- 编辑备注、关系、画像、我对 TA 的称呼
- 改名、删除、一键扫描清理无效联系人

### 群聊管理

- 启用/关闭自动回复，选择触发模式（全部 / @我 / 关键词）
- 主动聊天：设置话题和间隔，自动抓取热点发起对话
- 群成员画像：为每个成员设置角色、性格、说话风格、你对 TA 的称呼
- 群画像和回复策略编辑

### 消息记录

- 左侧对话列表，右侧聊天记录（气泡样式）
- 区分私聊和群聊，分页浏览

### 设置

- **我的人设** — 性格、说话风格、口头禅、语气、别人对你的称呼
- **自动分析** — 一键从真实聊天记录提取你的风格（自动排除 AI 生成的消息）
- **API 配置** — 分别配置回复和分析用的 API Key、Base URL、模型

### 审核 / 分析 / 调度

- 画像分析生成的建议需审核后才生效（通过/拒绝/编辑后应用）
- 支持批量分析调度策略配置

## 项目结构

```
src/
├── main.py                    # 消息监听主进程入口
├── agents/
│   ├── chat_agent.py          # 自动回复 Agent（消息聚合、人设模拟）
│   ├── proactive_chat.py      # 主动聊天（热点抓取、定时发送）
│   └── supervisor.py          # 聊天质量分析
├── backend/
│   ├── base.py                # 后端抽象接口
│   └── macos/
│       ├── backend.py         # macOS 后端实现
│       ├── automator.py       # AppleScript UI 自动化（搜索、点击、发送）
│       └── message_monitor.py # DB 解密消息监听（SQLCipher + WAL）
├── control/
│   ├── api/
│   │   ├── app.py             # FastAPI 应用（含静态文件托管）
│   │   └── routes/            # API 路由（联系人/群聊/规则/分析/审核/设置）
│   ├── services/              # 业务服务层（分析/审核/规则）
│   ├── repositories/          # 数据访问层
│   └── schemas/               # API 数据模型
├── core/
│   ├── config.py              # YAML 配置管理
│   ├── context.py             # SQLite 数据库管理（WAL 模式）
│   ├── security.py            # 敏感词过滤、频率限制、暂停关键词
│   ├── style.py               # 聊天风格管理（per-contact/group YAML）
│   └── scheduler.py           # APScheduler 任务调度
└── models/
    └── schemas.py             # Pydantic 数据模型

frontend/                      # React + Vite + TypeScript
├── src/
│   ├── api/client.ts          # API 客户端（全部端点）
│   ├── components/            # Layout, EditableField
│   └── pages/                 # Dashboard, Contacts, Groups, Messages, Reviews, Settings...
└── vite.config.ts             # Vite 配置（含 API 代理）

styles/                        # 聊天规则配置（YAML，支持 per-contact/group）
├── default.yaml               # 全局默认规则
├── contacts/_template.yaml    # 联系人规则模板
└── groups/_template.yaml      # 群聊规则模板

data/                          # 运行时数据（不入版本控制）
├── agent.db                   # SQLite 数据库
└── wechat_keys.json           # WeChat 加密密钥
```

## 配置参考

### config.yaml

```yaml
wechat:
  backend: "macos"

claude:
  chat_model: "claude-sonnet-4-6"
  supervisor_model: "claude-opus-4-6"

user:
  name: "你的昵称"

reply_rules:
  private_chat:
    whitelist_only: true        # 只回复白名单联系人
    max_reply_length: 200
    delay_range: [2, 8]         # 回复延迟范围（秒），模拟真人
    history_limit: 20           # 参考最近多少条消息
  group_chat:
    delay_range: [3, 15]
    history_limit: 30
    collect_window: 10          # 群聊消息聚合等待时间（秒）
    max_reply_length: 200

security:
  rate_limit: 30                # 每小时每联系人最大回复数
  pause_keyword: "#人工"        # 对方发送此关键词暂停自动回复
```

### styles/default.yaml

```yaml
chat_rules:
  tone: "随意、自然"
  reply_length: "通常1-2句话"
  emoji_usage: "少用"
  forbidden_patterns:
    - "作为AI"
    - "我来为你"
    - "以下是"
```

## 注意事项

- 密钥在 WeChat/Mac 重启后会变，需重新提取
- 需要给终端辅助功能权限（系统设置 → 隐私与安全 → 辅助功能）
- 自动回复通过 AppleScript 模拟操作发送，发送时 WeChat 窗口会被激活
- 所有 AI 生成的消息在数据库中有标记，用户画像分析时自动排除
- 控制台和消息监听是两个独立进程，通过 SQLite WAL 模式共享数据
- 本项目仅供学习和个人使用，请遵守微信使用条款

## 贡献

欢迎提交 Issue 和 Pull Request。

## License

MIT
