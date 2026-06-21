"""
Twitter/X 爬虫 — 通过 xurl CLI 抓取时间线推文。
UID: tw:<tweet_id>

增量机制：
- 按时间从新到旧遍历，连续命中已知UID后提前停止
- 默认每分钟检查，推文量可控

依赖：xurl CLI（已认证）+ HTTPS_PROXY（需要走 Clash 代理）
"""
import json
import os
import re
import subprocess
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Set

from .base import Article, BaseCrawler

# 北京时间 (UTC+8)
CST = timezone(timedelta(hours=8))

# xurl 命令完整路径
XURL = os.path.expanduser("~/.local/bin/xurl")

# proxy 环境变量（xurl 走 Clash 才能访问 X API）
PROXY_ENV = {**os.environ, "HTTPS_PROXY": "http://127.0.0.1:7890"}


def _strip_rt(text: str) -> str:
    """去掉 RT @user: 前缀，还原原文内容"""
    m = re.match(r'^RT @\w+:\s*', text)
    return text[m.end():] if m else text


def _utc_to_cst(utc_str: str) -> str:
    """将 UTC ISO 时间转为北京时间可读字符串 'YYYY-MM-DD HH:MM'"""
    if not utc_str:
        return ""
    try:
        # 解析 ISO 8601: "2026-06-19T16:01:10.000Z"
        dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        dt_cst = dt.astimezone(CST)
        return dt_cst.strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return utc_str  # 解析失败原样返回


class TwitterCrawler(BaseCrawler):
    """Twitter 爬虫

    支持的模式（config.mode）:
    - "timeline" (默认): 首页时间线，获取关注账号的推文
    - "list": 指定列表（需 config.list_id）

    过滤规则（config.filters）:
    - skip_rts: 跳过转推
    - skip_replies: 跳过回复（@开头）
    - min_engagement: 最低互动量（like+retweet+reply）
    """

    def __init__(self, config: dict = None):
        super().__init__(source_key="twitter", prefix="tw", config=config)
        self.mode = self.config.get("mode", "timeline")
        self.filters = self.config.get("filters", {})
        self._user_cache = {}  # author_id -> username

    def _xurl(self, *args, timeout: int = 30) -> dict:
        """调用 xurl CLI，返回解析后的 JSON"""
        cmd = [XURL] + list(args)
        result = None
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=PROXY_ENV,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("xurl timeout")

        if result is None or result.returncode != 0:
            stderr = (result.stderr if result else "")[:200]
            raise RuntimeError(f"xurl failed: {stderr}")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"xurl returned invalid JSON: {(result.stdout or '')[:200]}")

    def _fetch_timeline(self, max_results: int = 50) -> List[dict]:
        """抓取首页时间线（原始推文列表），一次性请求"""
        args = ["timeline", "-n", str(min(max_results, 100))]
        data = self._xurl(*args, timeout=30)
        
        tweets = data.get("data", [])
        
        # 缓存用户信息
        for user in data.get("includes", {}).get("users", []):
            self._user_cache[user["id"]] = user["username"]
        
        return tweets[:max_results]

    def _tweet_to_article(self, tweet: dict) -> Article:
        """将原始推文数据转为 Article"""
        tid = tweet["id"]
        text = tweet.get("text", "")
        created_at = tweet.get("created_at", "")

        # 去掉 RT 前缀作为显示文案
        display_text = _strip_rt(text)
        title = display_text[:100]
        if len(display_text) > 100:
            title = title[:97] + "..."

        # 构造推文链接
        author_id = tweet.get("author_id", "")
        username = self._user_cache.get(author_id, "i")
        url = f"https://x.com/{username}/status/{tid}"
        author = f"@{username}" if username != "i" else ""
        author_url = f"https://x.com/{username}" if username != "i" else ""

        # 互动量
        metrics = tweet.get("public_metrics", {})
        engagement = metrics.get("like_count", 0) + metrics.get("retweet_count", 0) + metrics.get("reply_count", 0)

        return Article(
            uid=self._make_uid(tid),
            source=self.source_key,
            title=title,
            url=url,
            content=display_text,
            published_at=_utc_to_cst(created_at),
            author=author,
            author_url=author_url,
        )

    def _should_skip(self, tweet: dict) -> bool:
        """根据过滤规则判断是否跳过"""
        if not self.filters:
            return False

        # 跳过转推
        if self.filters.get("skip_rts") and tweet.get("text", "").startswith("RT "):
            return True

        # 跳过纯回复
        if self.filters.get("skip_replies"):
            mentions = tweet.get("entities", {}).get("mentions", [])
            text = tweet.get("text", "")
            if mentions and text.strip().startswith("@"):
                return True

        # 最低互动量
        min_eng = self.filters.get("min_engagement", 0)
        if min_eng > 0:
            metrics = tweet.get("public_metrics", {})
            eng = metrics.get("like_count", 0) + metrics.get("retweet_count", 0) + metrics.get("reply_count", 0)
            if eng < min_eng:
                return True

        return False

    def fetch_new(self, known_uids: Set[str] = None) -> List[Article]:
        """抓取新推文，支持增量早停。
        
        API 返回的 Home Timeline 可能有算法插序，
        这里先按 created_at 严格倒序排序，确保增量早停逻辑正确。
        """
        raw_tweets = self._fetch_timeline(max_results=50)
        
        # 按 created_at 严格倒序（最新在前），消除 API 的算法排序干扰
        raw_tweets.sort(key=lambda t: t.get("created_at", ""), reverse=True)
        if not known_uids:
            return [self._tweet_to_article(t) for t in raw_tweets if not self._should_skip(t)]

        new_articles = []
        consecutive_hits = 0

        for tweet in raw_tweets:
            uid = self._make_uid(tweet["id"])

            if uid in known_uids:
                consecutive_hits += 1
                if self._should_stop(consecutive_hits):
                    break
            else:
                consecutive_hits = 0
                if not self._should_skip(tweet):
                    new_articles.append(self._tweet_to_article(tweet))

        return new_articles

    def fetch_detail(self, url: str) -> dict:
        """推文本身就是短内容，无需二次抓取。返回空，让引擎用 title 字段。"""
        return {"content": ""}
