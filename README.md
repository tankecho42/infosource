# InfoSource — 多源信息推荐系统

统一接入多个信息来源（领研网、Twitter、...），自动抓取、智能筛选、卡片推送、反馈学习。

## 架构

```
infosource/
├── feeds.db              # SQLite数据库（WAL模式）
├── db.py                 # 数据库连接+初始化
├── engine.py             # 推荐引擎（打分+探索+反馈学习）
├── card.py               # 统一飞书卡片发送
├── manage.py             # 来源管理工具
├── scheduler.py          # 调度器（增量抓取+去重入库）
├── crawlers/
│   ├── base.py           # 爬虫基类（新来源继承它）
│   └── linkresearcher.py # 领研网适配器
└── card_cache/           # 按uid缓存卡片JSON
```

## 数据库设计

| 表 | 说明 |
|---|---|
| `sources` | 来源注册（key/name/prefix/开关/间隔/统计） |
| `articles` | 文章池（uid带前缀如`lr:xxx`/source/published_at） |
| `pushed` | 推送记录（含摘要/分数/反馈） |
| `preferences` | 推荐偏好（KV存储JSON） |

## 核心特性

- **增量抓取**：爬虫接收已知UID集合，连续命中即停止
- **探索机制**：避免信息茧房，冷门领域有概率被推荐
- **反馈学习**：按钮反馈实时调整权重（感兴趣 +0.15 / 不感兴趣 -0.20）
- **多源统一**：UID带来源前缀（`lr:`/`tw:`），跨源不冲突

## 接入新来源

1. 写爬虫继承 `BaseCrawler`，实现 `fetch_new(known_uids)` + `fetch_detail(url)`
2. 在 `scheduler.py` 注册爬虫类
3. 在 `card.py` 的 `_source_meta()` 加来源元信息
4. `python3 manage.py add <key> <name> <prefix>`

## 使用

```bash
# 来源管理
python3 manage.py list
python3 manage.py add twitter Twitter tw --interval 30
python3 manage.py toggle twitter

# 手动检查新文章
python3 scheduler.py check --source linkresearcher

# 打分筛选
python3 engine.py score

# 查看偏好与统计
python3 engine.py prefs

# 发送卡片
python3 card.py push --uid "lr:xxx" --title "标题" --summary "摘要" --source linkresearcher
```

## 运行环境

- Python 3.11+
- 依赖：httpx
- 定时任务：cron `*/30 * * * *`（agent-driven，自动抓取+筛选+推送）

---

Created by TankEcho 🐻
