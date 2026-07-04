"""
短评爬虫：从 MySQL 获取 movie_id 列表，抓取豆瓣短评。

运行方式:
    scrapy crawl comment -a movie_ids=1291546,1291547    # 指定电影ID
    scrapy crawl comment -a max_pages=5                   # 每部电影最多翻5页
    scrapy crawl comment -a max_movies=10                 # 最多从10部电影抓评论
"""

import re
import logging

import scrapy
import pymysql

from crawler.items import CommentItem

logger = logging.getLogger(__name__)

COMMENT_URL = "https://movie.douban.com/subject/{movie_id}/comments"
COMMENT_API = "https://movie.douban.com/subject/{movie_id}/comments?start={start}&limit=20&status=P&sort=new_score"


class CommentSpider(scrapy.Spider):
    name = "comment"
    allowed_domains = ["movie.douban.com", "douban.com"]

    def __init__(self, movie_ids=None, max_pages=None, max_movies=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_movie_ids = (
            [int(x.strip()) for x in movie_ids.split(",") if x.strip()]
            if movie_ids
            else []
        )
        self.max_pages = int(max_pages) if max_pages else None
        self.max_movies = int(max_movies) if max_movies else None
        self.movie_crawled = 0

    def start_requests(self):
        if self.target_movie_ids:
            movie_ids = self.target_movie_ids
        else:
            # 从 MySQL 读取已有电影ID
            movie_ids = self._get_movie_ids_from_db()

        logger.info("CommentSpider will crawl %d movies", len(movie_ids))

        for movie_id in movie_ids:
            if self.max_movies and self.movie_crawled >= self.max_movies:
                break
            self.movie_crawled += 1
            url = COMMENT_URL.format(movie_id=movie_id)
            yield scrapy.Request(
                url,
                callback=self.parse_comment_list,
                meta={
                    "movie_id": movie_id,
                    "start": 0,
                    "pages_done": 0,
                },
            )

    def _get_movie_ids_from_db(self):
        """从 MySQL movie 表获取所有已抓取电影 ID"""
        try:
            conn = pymysql.connect(
                host="127.0.0.1",
                port=3306,
                user="crawler",
                password="123456",
                database="douban_movie",
                charset="utf8mb4",
            )
            cursor = conn.cursor()
            cursor.execute("SELECT movie_id FROM movie ORDER BY movie_id")
            ids = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            return ids
        except Exception as e:
            logger.error("Failed to fetch movie IDs from MySQL: %s", e)
            return []

    def parse_comment_list(self, response):
        """短评列表页 — 提取评论卡片"""
        movie_id = response.meta["movie_id"]
        start = response.meta.get("start", 0)

        comment_nodes = response.xpath(
            '//div[@class="comment-item"] | //div[contains(@class, "comment-item")]'
        )
        if not comment_nodes:
            # 兼容旧版页面结构
            comment_nodes = response.xpath('//div[@class="comment"]')

        for node in comment_nodes:
            item = CommentItem()
            item["movie_id"] = movie_id

            item["nickname"] = self._extract(
                node,
                './/span[@class="comment-info"]/a[1]/text()',
            )
            item["useful_num"] = self._extract_int(
                node,
                './/span[contains(@class, "votes")]/text()',
            )
            item["content"] = self._extract(
                node,
                './/span[@class="short"]/text()',
                './/p[@class="comment-content"]/text()',
            )
            item["comment_time"] = self._extract(
                node,
                './/span[contains(@class, "comment-time")]/@title',
                './/span[contains(@class, "comment-time")]/text()',
            )

            yield item

        # 翻页
        pages_done = response.meta.get("pages_done", 0) + 1
        if self.max_pages and pages_done >= self.max_pages:
            return

        next_start = start + 20
        if next_start < 200:  # 豆瓣短评最多翻到200条左右
            next_url = COMMENT_API.format(movie_id=movie_id, start=next_start)
            yield scrapy.Request(
                next_url,
                callback=self.parse_comment_list,
                meta={
                    "movie_id": movie_id,
                    "start": next_start,
                    "pages_done": pages_done,
                },
            )

    def _extract(self, selector, *xpaths):
        for xpath in xpaths:
            val = selector.xpath(xpath).get()
            if val:
                return val.strip()
        return ""

    def _extract_int(self, selector, *xpaths):
        val = self._extract(selector, *xpaths)
        if val:
            match = re.search(r"\d+", val.replace(",", ""))
            if match:
                return int(match.group())
        return 0
