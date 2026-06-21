"""
领研网爬虫 — 继承 BaseCrawler，实现 fetch_new() 和 fetch_detail()。
增量机制：利用领研网文章URL中的UUID作为UID，连续命中已知UID后停止。
"""
import re
import urllib.request
from typing import List, Set

from .base import Article, BaseCrawler

BASE = "https://www.linkresearcher.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


class LinkResearcherCrawler(BaseCrawler):
    """领研网爬虫

    UID: lr:<UUID>  (领研网文章URL中的UUID，全局唯一且稳定)
    增量: 首页一次请求拿到全部文章列表，在解析阶段按出现顺序判断是否已知。
          由于首页文章是按时间排的，连续命中STOP_AFTER_HITS个已知UID即停。
    """

    def __init__(self, config: dict = None):
        super().__init__(source_key="linkresearcher", prefix="lr", config=config)

    def _fetch_html(self, url: str) -> str:
        req = urllib.request.Request(url, headers=HEADERS)
        return urllib.request.urlopen(req, timeout=20).read().decode("utf-8")

    def _parse_all_articles(self, html: str) -> List[Article]:
        """从首页HTML提取所有文章（保持页面出现顺序）。"""
        articles = []
        seen_uids = set()

        def add(raw_uid, title, url, article_type):
            uid = self._make_uid(raw_uid)
            if uid in seen_uids:
                return
            if any(skip in title for skip in ["润色", "专刊", "广告"]):
                return
            seen_uids.add(uid)
            articles.append(Article(uid=uid, source=self.source_key, title=title, url=url))

        # 方法1: 带 title 属性的链接（轮播图）
        for m in re.finditer(
            r'href="(https://www\.linkresearcher\.com/information/([a-f0-9-]+))"[^>]*?title="([^"]{8,})"',
            html,
        ):
            add(m.group(2), m.group(3).strip(), m.group(1), "headline")

        # 方法2: 新闻卡片
        for m in re.finditer(
            r'href="https://www\.linkresearcher\.com/information/([a-f0-9-]+)"\s+target="blank">'
            r'.*?<div>([^<]{8,})</div>',
            html, re.DOTALL,
        ):
            uid, title = m.group(1), m.group(2).strip()
            if not re.match(r'^\d{4}/', title):
                add(uid, title, f"{BASE}/information/{uid}", "news")

        # 方法3: 科研圈日报
        daily_titles = re.findall(r'(?<=<p><span>)([^<]{10,})', html)
        for i, m in enumerate(re.finditer(
            r'/information/([a-f0-9-]+)"\s+target="blank">\s*<div>\s*<div>(20\d{2}/\d{2}/\d{2})</div>',
            html,
        )):
            title = daily_titles[i] if i < len(daily_titles) else "科研圈日报"
            add(m.group(1), title, f"{BASE}/information/{m.group(1)}", "daily")

        # 方法4: 排行榜
        for uid, title in re.findall(
            r'/information/([a-f0-9-]+)"\s+target="blank"><span>\d+</span><span>([^<]{8,})</span>',
            html,
        ):
            add(uid, title.strip(), f"{BASE}/information/{uid}", "ranked")

        return articles

    def fetch_new(self, known_uids: Set[str] = None) -> List[Article]:
        """抓取文章列表，支持增量早停。

        Args:
            known_uids: 已知的UID集合（带lr:前缀）。连续命中3个即停。
        """
        html = self._fetch_html(BASE + "/")
        all_articles = self._parse_all_articles(html)

        if not known_uids:
            return all_articles

        new_articles = []
        consecutive_hits = 0
        for a in all_articles:
            if a.uid in known_uids:
                consecutive_hits += 1
                if self._should_stop(consecutive_hits):
                    break
            else:
                consecutive_hits = 0  # 遇到新文章重置计数
                new_articles.append(a)

        return new_articles

    def fetch_detail(self, url: str) -> dict:
        try:
            html = self._fetch_html(url)
            m = re.search(r'name="description"\s+content="([^"]{20,})"', html)
            content = m.group(1).strip() if m else ""
            m2 = re.search(r"<title>([^<]+)</title>", html)
            title = m2.group(1).strip() if m2 else ""
            # 尝试提取发布时间
            published_at = self._extract_publish_time(html)
            return {"title": title, "url": url, "content": content, "published_at": published_at}
        except Exception:
            return {"title": "", "url": url, "content": "", "published_at": ""}

    @staticmethod
    def _extract_publish_time(html: str) -> str:
        """尝试从文章页HTML提取发布时间"""
        # 方法1: meta标签 article:published_time / og:updated_time
        for prop in ("article:published_time", "og:published_time", "og:updated_time", "publishdate", "datePublished"):
            m = re.search(rf'property="{prop}"\s+content="([^"]+)"', html)
            if m:
                return m.group(1).strip()
        # 方法2: JSON-LD datePublished
        m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
        if m:
            return m.group(1).strip()
        # 方法3: 领研网页面上的日期格式 如 2025-03-15 或 2025/03/15
        m = re.search(r'(20\d{2}[-/]\d{2}[-/]\d{2})', html[:3000])
        if m:
            return m.group(1)
        return ""
