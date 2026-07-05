"""
短评爬虫：从 MySQL 取 movie_id，按热度排序，抓取短评。

运行方式:
    scrapy crawl comment -a max_movies=10 -a max_pages=2   # 测试
    scrapy crawl comment -a max_movies=5000                 # 爬 5000 部热门电影
    scrapy crawl comment                                    # 爬全部 (6.7万部)
"""

import re
import logging

import scrapy
import pymysql

from crawler.items import CommentItem

logger = logging.getLogger(__name__)

COMMENT_URL = "https://movie.douban.com/subject/{movie_id}/comments"
COMMENT_PAGE = "https://movie.douban.com/subject/{movie_id}/comments?start={start}&limit=20&status=P&sort=new_score"


class CommentSpider(scrapy.Spider):
    name = "comment"
    allowed_domains = ["movie.douban.com", "douban.com"]

    def __init__(self, max_movies=None, max_pages=None, movie_ids=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_movies = int(max_movies) if max_movies else None
        self.max_pages = int(max_pages) if max_pages else 5  # 默认每部5页
        self.target_ids = (
            [int(x.strip()) for x in movie_ids.split(",") if x.strip()]
            if movie_ids else []
        )
        self.movie_index = 0
        self.total_scraped = 0

    def start_requests(self):
        if self.target_ids:
            movie_ids = self.target_ids
        else:
            # 按评价人数降序 (优先热门电影)
            movie_ids = self._load_movie_ids(limit=self.max_movies)

        logger.info("CommentSpider: %d movies, max %d pages each", len(movie_ids), self.max_pages)

        for movie_id in movie_ids:
            self.movie_index += 1
            url = COMMENT_URL.format(movie_id=movie_id)
            yield scrapy.Request(
                url,
                callback=self.parse_comments,
                meta={"movie_id": movie_id, "start": 0, "page": 0},
                errback=self._handle_error,
            )

    def _load_movie_ids(self, limit=None):
        """从 MySQL 加载电影 ID，按评价人数降序"""
        try:
            conn = pymysql.connect(
                host="127.0.0.1", port=3306, user="crawler",
                password="123456", database="douban_movie", charset="utf8mb4",
            )
            cursor = conn.cursor()
            sql = "SELECT movie_id FROM movie ORDER BY rating_count DESC"
            cursor.execute(sql)
            ids = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            if limit:
                ids = ids[:limit]
            return ids
        except Exception as e:
            logger.error("Failed to load movie IDs: %s", e)
            return []

    def parse_comments(self, response):
        movie_id = response.meta["movie_id"]
        start = response.meta["start"]
        page = response.meta["page"]

        nodes = response.xpath('//div[@class="comment-item"]')
        page_count = 0

        for node in nodes:
            content = self._xpath(node, './/span[@class="short"]/text()')
            if not content:
                continue

            item = CommentItem()
            item["movie_id"] = movie_id
            item["nickname"] = self._xpath(node, './/span[@class="comment-info"]/a[1]/text()')
            item["comment_time"] = (
                self._xpath(node, './/span[contains(@class, "comment-time")]/@title')
                or self._xpath(node, './/span[contains(@class, "comment-time")]/text()')
            )
            item["useful_num"] = self._xpath_int(node, './/span[contains(@class, "votes")]/text()')
            item["content"] = content

            yield item
            page_count += 1
            self.total_scraped += 1

        # 翻页
        if page + 1 < self.max_pages and page_count == 20:
            next_start = start + 20
            next_url = COMMENT_PAGE.format(movie_id=movie_id, start=next_start)
            yield scrapy.Request(
                next_url,
                callback=self.parse_comments,
                meta={"movie_id": movie_id, "start": next_start, "page": page + 1},
                errback=self._handle_error,
            )

        if self.movie_index % 50 == 0:
            logger.info("Progress: %d movies, %d comments scraped", self.movie_index, self.total_scraped)

    def _handle_error(self, failure):
        pass  # 静默跳过

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
