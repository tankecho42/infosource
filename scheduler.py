"""
InfoSource 调度器 — 核心入口
检查所有启用的来源，抓取新文章，去重入库。

Usage:
  python3 scheduler.py check [--source KEY]    # 检查新文章并入库
  python3 scheduler.py check --source KEY       # 只检查某来源
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db, safe_commit

# 爬虫注册表 — 新来源在这里注册一行
from crawlers.linkresearcher import LinkResearcherCrawler
from crawlers.twitter import TwitterCrawler

CRAWLER_REGISTRY = {
    "linkresearcher": LinkResearcherCrawler,
    "twitter": TwitterCrawler,
}


def check_source(source_key: str) -> dict:
    """检查单个来源的新文章，增量去重入库。返回统计信息。"""
    conn = get_db()

    # 确认来源存在且启用
    src = conn.execute("SELECT * FROM sources WHERE key=? AND enabled=1", (source_key,)).fetchone()
    if not src:
        conn.close()
        return {"source": source_key, "error": "not found or disabled"}

    # 实例化爬虫
    crawler_cls = CRAWLER_REGISTRY.get(source_key)
    if not crawler_cls:
        conn.close()
        return {"source": source_key, "error": "no crawler registered"}

    config = {}
    if src["config"]:
        try:
            config = json.loads(src["config"])
        except Exception:
            pass
    crawler = crawler_cls(config=config)

    # 从数据库查已知UID集合，传给爬虫实现增量早停
    known_rows = conn.execute("SELECT uid FROM articles WHERE source=?", (source_key,)).fetchall()
    known_uids = {r["uid"] for r in known_rows}

    # 抓取（增量模式）
    try:
        raw_articles = crawler.fetch_new(known_uids=known_uids)
    except Exception as e:
        conn.close()
        return {"source": source_key, "error": f"fetch failed: {e}"}

    # 二次去重（防爬虫返回已知文章）
    new_articles = [a for a in raw_articles if a.uid not in known_uids]

    # 入库
    for a in new_articles:
        conn.execute(
            "INSERT OR IGNORE INTO articles (uid, source, title, url, author, author_url, published_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (a.uid, a.source, a.title, a.url, a.author, a.author_url, a.published_at or None),
        )

    # 更新来源的 last_check
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE sources SET last_check=? WHERE key=?", (now, source_key))
    safe_commit(conn)
    conn.close()

    return {
        "source": source_key,
        "known": len(known_uids),
        "fetched": len(raw_articles),
        "new": len(new_articles),
        "new_articles": [{"uid": a.uid, "title": a.title, "url": a.url} for a in new_articles],
    }


def check_all() -> list:
    """检查所有启用的来源"""
    conn = get_db()
    sources = [r["key"] for r in conn.execute("SELECT key FROM sources WHERE enabled=1").fetchall()]
    conn.close()
    return [check_source(s) for s in sources]


def fetch_detail(source_key: str, url: str) -> dict:
    """通过来源的爬虫抓取文章正文"""
    crawler_cls = CRAWLER_REGISTRY.get(source_key)
    if not crawler_cls:
        return {"content": ""}
    crawler = crawler_cls()
    return crawler.fetch_detail(url)


def main():
    parser = argparse.ArgumentParser(description="InfoSource 调度器")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="检查新文章")
    c.add_argument("--source", default=None, help="只检查某来源")
    d = sub.add_parser("detail", help="抓取文章正文")
    d.add_argument("--source", required=True)
    d.add_argument("--url", required=True)
    args = parser.parse_args()

    if args.cmd == "check":
        if args.source:
            result = check_source(args.source)
        else:
            result = check_all()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.cmd == "detail":
        result = fetch_detail(args.source, args.url)
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
