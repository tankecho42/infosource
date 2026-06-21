"""
InfoSource 爬虫基类
所有来源爬虫继承此类，实现 fetch_new() 和 fetch_detail()。

增量机制：fetch_new() 接收 known_uids 集合，爬虫在遍历结果时
一旦连续命中已知UID就提前停止，避免无意义的全量抓取。
"""
import abc
from dataclasses import dataclass
from typing import List, Optional, Set


@dataclass
class Article:
    """统一文章结构"""
    uid: str          # 带来源前缀的UID，如 lr:abc-123, tw:1234567890
    source: str       # 来源key，如 linkresearcher
    title: str
    url: str
    content: str = ""  # 正文摘要
    published_at: str = ""  # 原始发布时间，ISO格式或可读字符串，空=未知


class BaseCrawler(abc.ABC):
    """爬虫基类 — 子类必须实现 fetch_new()

    增量抓取约定：
    - fetch_new(known_uids) 接收已知UID集合
    - 爬虫按时间从新到旧遍历，连续命中已知UID后可以提前停止
    - 返回的文章列表应只包含新文章（爬虫可自行过滤，也可全返回由调度器去重）
    - 子类通过 self._should_stop(hit_count) 判断是否该停
    """

    # 连续命中已知UID多少次后停止（子类可覆盖）
    STOP_AFTER_HITS = 3

    def __init__(self, source_key: str, prefix: str, config: dict = None):
        self.source_key = source_key
        self.prefix = prefix
        self.config = config or {}

    def _make_uid(self, raw_id: str) -> str:
        """构造带前缀的UID"""
        return f"{self.prefix}:{raw_id}"

    def _should_stop(self, consecutive_hits: int) -> bool:
        """判断是否该停止抓取"""
        return consecutive_hits >= self.STOP_AFTER_HITS

    @abc.abstractmethod
    def fetch_new(self, known_uids: Set[str] = None) -> List[Article]:
        """抓取新文章列表（不含正文），返回 Article 列表。

        Args:
            known_uids: 已知UID集合（带前缀）。爬虫应利用此参数实现增量抓取：
                        按时间从新到旧遍历，连续命中已知UID后可提前停止。
                        如果为None，则返回全部文章（首次运行）。
        """
        ...

    def fetch_detail(self, url: str) -> dict:
        """抓取单篇文章的正文摘要。
        子类可覆盖以实现正文抓取。默认返回空。
        """
        return {"content": ""}
