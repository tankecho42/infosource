# InfoSource 📡 — 多源信息推荐系统

统一接入多个信息来源（领研网、Twitter、RSS...），自动抓取、智能筛选、卡片推送、反馈学习。
每30分钟自动运行，根据你的兴趣偏好推送值得看的内容，越用越懂你。

## 系统架构

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│  Crawlers   │───▶│  Scheduler   │───▶│   Engine    │───▶│    Card      │
│ (各来源爬虫) │    │ (增量去重入库) │    │ (打分+探索)  │    │ (飞书卡片推送) │
└─────────────┘    └──────────────┘    └─────────────┘    └──────────────┘
                          │                   ▲                    │
                          ▼                   │                    ▼
                   ┌─────────────┐     ┌─────────────┐     ┌──────────────┐
                   │  SQLite DB  │     │  反馈按钮回调  │◀────│  用户点击反馈  │
                   │ (文章+推送+偏好)│     │ (实时更新权重) │     └──────────────┘
                   └─────────────┘     └─────────────┘
```

## 目录结构

```
infosource/
├── README.md
├── db.py                 # SQLite数据库（连接/初始化/偏好读写）
├── engine.py             # 推荐引擎（打分+探索+反馈学习+分类统计）
├── card.py               # 飞书交互卡片构建与发送
├── manage.py             # 来源管理CLI（注册/开关/统计）
├── scheduler.py          # 调度器（增量抓取+去重+入库+详情抓取）
├── crawlers/
│   ├── __init__.py
│   ├── base.py           # 爬虫抽象基类
│   └── linkresearcher.py # 领研网适配器
├── card_cache/           # 运行时生成：按uid缓存卡片JSON
└── feeds.db              # 运行时生成：SQLite数据库
```

## 数据库设计

| 表 | 用途 | 关键字段 |
|---|---|---|
| `sources` | 来源注册表 | `key`(唯一标识) `name`(显示名) `prefix`(UID前缀) `enabled`(开关) `check_interval`(分钟) |
| `articles` | 文章池 | `uid`(带前缀如`lr:xxx`) `source` `title` `url` `published_at` `pushed`(是否已推) |
| `pushed` | 推送记录 | `uid` `summary`(Echo摘要) `score` `feedback`(1好/-1差/NULL未反馈) |
| `preferences` | 推荐偏好 | KV存储，JSON值：`domain_weights` `keyword_weights` `category_stats` `exploration` |

## 前置要求

### 运行环境
- **Python 3.10+**
- **httpx**（HTTP请求）

```bash
pip install httpx
```

### 飞书机器人

需要一个**企业自建应用**（飞书开放平台创建），获取以下凭证：
- `App ID`
- `App Secret`

应用需要开通以下权限：
- `im:message:send_as_bot` — 发送消息
- `im:interactive` — 发送交互卡片
- `im:message.card_action.trigger` — 接收卡片按钮回调（反馈按钮）

### 卡片回调处理

反馈按钮的点击回调需要你的消息网关处理。本项目设计运行在 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 网关上，回调处理逻辑在 `gateway/platforms/feishu.py` 的 `_handle_custom_card_action()` 中。

如果你用自己的网关，需要实现：
1. 接收飞书 `card.action.trigger` 事件
2. 解析按钮 `value` 中的 `{"action":"feedback","rating":"good","uid":"lr:xxx"}`
3. 调用 `python3 engine.py record <rating> --uid <uid>`
4. 返回更新后的卡片（替换按钮组为已评价状态）

## 快速开始

### 1. 克隆 & 初始化

```bash
git clone https://github.com/tankecho42/infosource.git
cd infosource

# 初始化数据库
python3 db.py

# 注册第一个来源
python3 manage.py add linkresearcher "领研网" lr --interval 30
```

### 2. 配置飞书凭证

创建 `.env` 文件（与脚本同级目录）：

```env
FEISHU_APP_ID=cli_xxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
```

### 3. 设置推送目标

编辑 `card.py` 中的 `INFO_FLOW` 常量，改成你的飞书群 chat_id：

```python
INFO_FLOW = "oc_xxxxxxxxxxxxxxx"  # 你的飞书群ID
```

### 4. 测试

```bash
# 抓取领研网新文章
python3 scheduler.py check --source linkresearcher

# 打分筛选
python3 engine.py score linkresearcher

# 查看偏好与统计
python3 engine.py prefs

# 手动发一张测试卡片
python3 card.py push \
  --uid "lr:test001" \
  --title "测试文章" \
  --url "https://example.com" \
  --summary "这是一条测试摘要" \
  --score 2.0 \
  --source linkresearcher \
  --domains "AI,计算"
```

### 5. 定时运行

#### 方式一：crontab（纯脚本模式，不含LLM摘要）

```bash
# 每30分钟检查并推送（需自行实现摘要逻辑）
*/30 * * * * cd /path/to/infosource && python3 scheduler.py check && python3 engine.py score
```

#### 方式二：Hermes Agent cron（推荐，含LLM智能摘要）

在 Hermes 中创建 agent-driven cron job：

```yaml
schedule: "*/30 * * * *"
enabled_toolsets: ["terminal"]
prompt: |
  1. python3 scheduler.py check
  2. python3 engine.py score
  3. 对score>=0.5的文章，抓正文：python3 scheduler.py detail --source <key> --url <url>
  4. 用你的视角写2-3句精简摘要
  5. 逐条推送：python3 card.py push --uid ... --title ... --summary ... --source ...
```

## 接入新来源

以接入 Twitter 为例：

### 第1步：写爬虫

```python
# crawlers/twitter.py
from .base import Article, BaseCrawler
from typing import List, Set

class TwitterCrawler(BaseCrawler):
    # 连续命中5个已知推文才停（Twitter信息密度高）
    STOP_AFTER_HITS = 5

    def __init__(self, config: dict = None):
        super().__init__(source_key="twitter", prefix="tw", config=config)

    def fetch_new(self, known_uids: Set[str] = None) -> List[Article]:
        # 调Twitter API拿timeline
        tweets = self._fetch_timeline()
        articles = []
        hits = 0
        for t in tweets:
            uid = self._make_uid(str(t["id"]))
            if known_uids and uid in known_uids:
                hits += 1
                if self._should_stop(hits):
                    break
                continue
            hits = 0
            articles.append(Article(
                uid=uid,
                source=self.source_key,
                title=t["text"][:100],
                url=f"https://twitter.com/i/web/status/{t['id']}",
                published_at=t["created_at"],  # Twitter天然有精确时间
            ))
        return articles

    def fetch_detail(self, url: str) -> dict:
        return {"content": "", "published_at": ""}
```

### 第2步：注册爬虫

在 `scheduler.py` 的 `CRAWLER_REGISTRY` 加一行：

```python
from crawlers.twitter import TwitterCrawler

CRAWLER_REGISTRY = {
    "linkresearcher": LinkResearcherCrawler,
    "twitter": TwitterCrawler,  # ← 加这行
}
```

### 第3步：注册来源

```bash
python3 manage.py add twitter "Twitter" tw --interval 30
```

### 第4步：卡片来源标记

在 `card.py` 的 `_source_meta()` 加一行：

```python
def _source_meta(source):
    return {
        "linkresearcher": ("📰", "领研网", "blue"),
        "twitter":       ("🐦", "Twitter", "cyan"),  # ← 加这行
    }.get(source, ("📡", source or "未知", "blue"))
```

完成。重启后调度器会自动检查新来源。

## 推荐引擎说明

### 打分机制

每篇文章的分数 = 领域权重 + 关键词权重 + 时效性加分 + 长度惩罚 + **探索奖励**

### 探索机制（防信息茧房）

| 因子 | 触发条件 | 效果 |
|---|---|---|
| 新鲜度 | 领域曝光 < 全站平均 | +0.4 × 温度 |
| 不确定性 | 曝光≥3次但反馈率<30% | +0.2 × 温度 |
| 负面惩罚 | 反馈≥3次且总分<-1 | -0.3 |
| 随机扰动 | 每次打分 | 0~0.25 × 温度 |

探索温度从 1.0 开始，每推送一篇降 0.002，最低 0.3，系统越成熟探索越收敛但不消失。

### 反馈学习

| 操作 | 权重变化 |
|---|---|
| 感兴趣 | 领域 +0.15，关键词 +0.075 |
| 不感兴趣 | 领域 -0.20，关键词 -0.100 |

## 管理命令速查

```bash
# 来源管理
python3 manage.py list                          # 列出所有来源
python3 manage.py add <key> <name> <prefix>     # 注册新来源
python3 manage.py toggle <key>                  # 开关来源
python3 manage.py info <key>                    # 查看来源详情
python3 manage.py remove <key>                  # 删除来源

# 推荐引擎
python3 engine.py score [source]                # 打分筛选（可指定来源）
python3 engine.py record <rating> --uid <uid>   # 记录反馈（good/bad/meh）
python3 engine.py prefs                         # 查看偏好+分类统计
python3 engine.py reset                         # 重置偏好

# 调度器
python3 scheduler.py check [--source KEY]       # 增量抓取并入库
python3 scheduler.py detail --source KEY --url URL  # 抓取文章正文

# 卡片发送
python3 card.py push --uid ... --title ... --summary ... --source ... [--dry-run]
```

## License

MIT

---

Created by [TankEcho](https://github.com/tankecho42) 🐻
