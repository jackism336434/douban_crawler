"""
按类型/标签爬取豆瓣电影。

从 crawl_target 表读取目标，逐标签爬取：
  1. 访问豆瓣标签页 https://movie.douban.com/tag/{name}
  2. 从列表页提取电影链接，进入详情页
  3. 提取电影信息 → MovieItem（复用 movie_spider 的提取逻辑）
  4. 更新 crawl_target 状态

运行方式:
    scrapy crawl tag_movie                        # 默认: 每个标签 100 部
    scrapy crawl tag_movie -a per_tag=200         # 每个标签最多 200 部
    scrapy crawl tag_movie -a max_pages=5         # 每个标签最多翻 5 页
    scrapy crawl tag_movie -a test=1              # 测试: 只爬 1 个标签, 1 页
"""

import logging
import re
from urllib.parse import quote

import pymysql
import scrapy

from crawler.items import MovieItem

logger = logging.getLogger(__name__)

TAG_LIST_URL = "https://movie.douban.com/tag/{}?start={}&type=T"


class TagMovieSpider(scrapy.Spider):
    name = "tag_movie"
    allowed_domains = ["movie.douban.com", "douban.com"]

    def __init__(self, per_tag=None, max_pages=None, test=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.per_tag = int(per_tag) if per_tag else 100
        self.max_pages = int(max_pages) if max_pages else 10
        self.test_mode = test is not None

        # Per-tag tracking
        self._current_target_id = None
        self._current_count = 0

        # Load existing movie IDs to skip
        self._seen_ids = set()

    # ── Startup ────────────────────────────────────────────────

    def start_requests(self):
        self._load_seen_ids()
        targets = self._load_targets()

        if not targets:
            logger.warning("No crawl targets found in database.")
            return

        logger.info("Loaded %d crawl targets", len(targets))

        for t in targets:
            tid, name, ttype = t["id"], t["target_name"], t["target_type"]
            self._set_target_status(tid, "running")

            # 每个标签从 offset=0 开始
            tag_encoded = quote(name)
            start_url = TAG_LIST_URL.format(tag_encoded, 0)

            yield scrapy.Request(
                start_url,
                callback=self.parse_tag_list,
                meta={
                    "target_id": tid,
                    "target_name": name,
                    "target_type": ttype,
                    "page": 0,
                    "tag_count": 0,
                },
                dont_filter=True,
            )

            if self.test_mode:
                break

    # ── Tag list page ──────────────────────────────────────────

    def parse_tag_list(self, response):
        tid = response.meta["target_id"]
        name = response.meta["target_name"]
        page = response.meta["page"]
        tag_count = response.meta["tag_count"]

        # 提取列表中的电影链接
        movie_links = response.xpath(
            '//a[@class="nbg" and contains(@href, "/subject/")]/@href'
        ).getall()

        if not movie_links:
            # 回退选择器
            movie_links = response.xpath(
                '//div[contains(@class, "pl2")]//a[contains(@href, "/subject/")]/@href'
            ).getall()

        for link in movie_links:
            if self.per_tag and tag_count >= self.per_tag:
                break
            if self.test_mode and tag_count >= 5:
                break

            match = re.search(r"/subject/(\d+)/?", link)
            if not match:
                continue
            mid = int(match.group(1))
            if mid in self._seen_ids:
                continue

            self._seen_ids.add(mid)
            tag_count += 1

            yield response.follow(
                link,
                callback=self.parse_movie_detail,
                meta={"movie_id": mid, "target_id": tid, "target_name": name},
                errback=self._handle_error,
            )

        logger.info(
            "[%s] page %d: found %d links, dispatched %d total",
            name, page + 1, len(movie_links), tag_count,
        )

        # Pagination: next page
        next_page = response.xpath(
            '//span[@class="next"]/a/@href'
        ).get()

        if (
            next_page
            and (not self.per_tag or tag_count < self.per_tag)
            and page + 1 < self.max_pages
            and not (self.test_mode and page >= 1)
        ):
            yield response.follow(
                next_page,
                callback=self.parse_tag_list,
                meta={
                    "target_id": tid,
                    "target_name": name,
                    "page": page + 1,
                    "tag_count": tag_count,
                },
                dont_filter=True,
            )
        else:
            # 本标签完成
            self._finish_target(tid, tag_count)
            logger.info("[%s] Done: %d movies dispatched", name, tag_count)

    # ── Movie detail page ──────────────────────────────────────

    def parse_movie_detail(self, response):
        movie_id = response.meta["movie_id"]

        item = self._extract_movie(response, movie_id)
        if item.get("movie_name"):
            self._current_count += 1
            if self._current_count % 50 == 0:
                logger.info("Scraped %d movies in this run", self._current_count)
            yield item

    # ── Field extraction (same logic as movie_spider) ──────────

    def _extract_movie(self, response, movie_id):
        item = MovieItem()
        item["movie_id"] = movie_id

        item["movie_name"] = (
            self._xpath(response, '//span[@property="v:itemreviewed"]/text()')
            or self._xpath(response, '//title/text()')
        )
        item["poster_url"] = self._xpath(response, '//img[@rel="v:image"]/@src')
        item["intro"] = self._xpath(response, '//span[@property="v:summary"]/text()')

        item["directors"] = response.xpath('//a[@rel="v:directedBy"]/text()').getall()
        item["writers"] = self._person_list(response, "编剧")
        item["actors"] = response.xpath('//a[@rel="v:starring"]/text()').getall()[:5]
        item["genres"] = response.xpath('//span[@property="v:genre"]/text()').getall()

        info_text = "".join(response.xpath('//div[@id="info"]//text()').getall())
        if info_text:
            item["country"] = self._re_field(info_text, r"制片国家/地区:\s*(.+?)(?:\n|$)")
            item["language"] = self._re_field(info_text, r"语言:\s*(.+?)(?:\n|$)")
            item["release_date"] = self._re_field(info_text, r"上映日期:\s*(.+?)(?:\n|$)")
            item["duration"] = self._re_field(info_text, r"片长:\s*(.+?)(?:\n|$)")
            item["imdb_url"] = self._re_field(info_text, r"IMDb:\s*(.+?)(?:\n|$)")
            item["alias_name"] = self._re_field(info_text, r"又名:\s*(.+?)(?:\n|$)")

        item["douban_score"] = self._xpath(response, '//strong[@property="v:average"]/text()')
        item["rating_count"] = self._xpath_int(response, '//span[@property="v:votes"]/text()')
        item["comment_count"] = self._xpath_int(
            response, '//div[@id="comments-section"]//span[@class="pl"]/a/text()',
        )
        item["review_count"] = self._xpath_int(
            response, '//section[contains(@class, "review")]//span[@class="pl"]/a/text()',
        )

        return item

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _xpath(selector, *xpaths):
        for xpath in xpaths:
            val = selector.xpath(xpath).get()
            if val:
                return val.strip()
        return ""

    @staticmethod
    def _xpath_int(selector, *xpaths):
        for xpath in xpaths:
            val = selector.xpath(xpath).get()
            if val:
                match = re.search(r"\d+", val.replace(",", ""))
                if match:
                    return int(match.group())
        return 0

    @staticmethod
    def _person_list(selector, role_label):
        names = selector.xpath(
            f'//span[contains(text(), "{role_label}")]'
            '/following-sibling::span[1]//a[contains(@href, "/celebrity/")]/text()'
        ).getall()
        return [n.strip() for n in names if n.strip()]

    @staticmethod
    def _re_field(text, pattern):
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
        return ""

    def _handle_error(self, failure):
        pass

    # ── Database helpers ───────────────────────────────────────

    def _db_conn(self):
        return pymysql.connect(
            host="127.0.0.1", port=3306, user="crawler", password="123456",
            database="douban_movie", charset="utf8mb4",
        )

    def _load_seen_ids(self):
        """Load already-scraped movie IDs to avoid duplicates."""
        try:
            conn = self._db_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT movie_id FROM movie")
            ids = {row[0] for row in cursor.fetchall()}
            self._seen_ids = ids
            cursor.close()
            conn.close()
            logger.info("Loaded %d existing movie IDs", len(ids))
        except Exception as e:
            logger.warning("Failed to load existing IDs: %s", e)

    def _load_targets(self):
        """Load crawl targets with status idle or pending."""
        try:
            conn = self._db_conn()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, target_name, target_type FROM crawl_target "
                "WHERE status IN ('idle', 'pending') "
                "ORDER BY id"
            )
            rows = [
                {"id": r[0], "target_name": r[1], "target_type": r[2]}
                for r in cursor.fetchall()
            ]
            cursor.close()
            conn.close()
            return rows
        except Exception as e:
            logger.error("Failed to load targets: %s", e)
            return []

    def _set_target_status(self, tid, status):
        try:
            conn = self._db_conn()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE crawl_target SET status = %s WHERE id = %s",
                (status, tid),
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            logger.error("Failed to update target %d status: %s", tid, e)

    def _finish_target(self, tid, count):
        try:
            conn = self._db_conn()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE crawl_target SET status = 'done', movie_count = %s, "
                "last_crawl_time = NOW() WHERE id = %s",
                (count, tid),
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            logger.error("Failed to finish target %d: %s", tid, e)
