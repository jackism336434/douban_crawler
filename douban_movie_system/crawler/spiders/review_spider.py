"""
影评爬虫：从 MySQL 取 movie_id，抓取长影评。

运行方式:
    scrapy crawl review -a max_movies=10 -a max_pages=2    # 测试
    scrapy crawl review -a max_movies=5000                  # 爬 5000 部热门电影
"""

import re
import logging

import scrapy
import pymysql

from crawler.items import ReviewItem

logger = logging.getLogger(__name__)

REVIEW_LIST_URL = "https://movie.douban.com/subject/{movie_id}/reviews"
REVIEW_DETAIL_URL = "https://movie.douban.com/review/{review_id}/"


class ReviewSpider(scrapy.Spider):
    name = "review"
    allowed_domains = ["movie.douban.com", "douban.com"]

    def __init__(self, max_movies=None, max_pages=None, movie_ids=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_movies = int(max_movies) if max_movies else None
        self.max_pages = int(max_pages) if max_pages else 3
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
            movie_ids = self._load_movie_ids(limit=self.max_movies)

        logger.info("ReviewSpider: %d movies, max %d pages each", len(movie_ids), self.max_pages)

        for movie_id in movie_ids:
            self.movie_index += 1
            url = REVIEW_LIST_URL.format(movie_id=movie_id)
            yield scrapy.Request(
                url,
                callback=self.parse_review_list,
                meta={"movie_id": movie_id, "page": 0},
                errback=self._handle_error,
            )

    def _load_movie_ids(self, limit=None):
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

    def parse_review_list(self, response):
        """影评列表页 — 提取每条影评链接，跟进详情页"""
        movie_id = response.meta["movie_id"]
        page = response.meta["page"]

        review_links = response.xpath(
            '//div[contains(@class, "review-list")]'
            '//a[contains(@href, "/review/")]/@href'
        ).getall()

        for link in review_links:
            match = re.search(r"/review/(\d+)/?", link)
            if not match:
                continue
            review_id = match.group(1)
            detail_url = REVIEW_DETAIL_URL.format(review_id=review_id)
            yield response.follow(
                detail_url,
                callback=self.parse_review_detail,
                meta={"movie_id": movie_id},
                errback=self._handle_error,
            )

        # 翻页
        if page + 1 < self.max_pages:
            next_page = response.xpath('//span[@class="next"]/a/@href').get()
            if next_page:
                yield response.follow(
                    next_page,
                    callback=self.parse_review_list,
                    meta={"movie_id": movie_id, "page": page + 1},
                    errback=self._handle_error,
                )

        if self.movie_index % 50 == 0:
            logger.info("Progress: %d movies, %d reviews scraped", self.movie_index, self.total_scraped)

    def parse_review_detail(self, response):
        """影评详情页 — 提取完整内容"""
        movie_id = response.meta["movie_id"]

        content_parts = response.xpath(
            '//div[contains(@class, "review-content")]//p/text()'
        ).getall()
        content = "\n".join(p.strip() for p in content_parts if p.strip())

        if not content:
            return

        item = ReviewItem()
        item["movie_id"] = movie_id
        item["content"] = content
        item["nickname"] = self._xpath(
            response,
            '//header//a[contains(@class, "name")]/text()',
            '//span[contains(@class, "name")]/text()',
        )
        item["review_time"] = self._xpath(
            response,
            '//span[contains(@class, "main-meta")]/text()',
        )
        item["useful_num"] = self._xpath_int(response, '//button[contains(@class, "useful")]/text()')
        item["useless_num"] = self._xpath_int(response, '//button[contains(@class, "useless")]/text()')

        self.total_scraped += 1
        yield item

    def _handle_error(self, failure):
        pass

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
