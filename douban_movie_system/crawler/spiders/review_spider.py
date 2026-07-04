"""
影评爬虫：抓取豆瓣电影长影评。

运行方式:
    scrapy crawl review -a movie_ids=1291546       # 指定电影ID
    scrapy crawl review -a max_pages=5              # 每部电影最多翻5页
    scrapy crawl review -a max_movies=10            # 最多抓10部电影
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
            movie_ids = self._get_movie_ids_from_db()

        logger.info("ReviewSpider will crawl %d movies", len(movie_ids))

        for movie_id in movie_ids:
            if self.max_movies and self.movie_crawled >= self.max_movies:
                break
            self.movie_crawled += 1
            url = REVIEW_LIST_URL.format(movie_id=movie_id)
            yield scrapy.Request(
                url,
                callback=self.parse_review_list,
                meta={
                    "movie_id": movie_id,
                    "start": 0,
                    "pages_done": 0,
                },
            )

    def _get_movie_ids_from_db(self):
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

    def parse_review_list(self, response):
        """影评列表页 — 提取每条影评的链接与元数据，进入详情页"""
        movie_id = response.meta["movie_id"]

        review_cards = response.xpath(
            '//div[contains(@class, "review-list")]//div[contains(@class, "review-item")]'
            '| //div[@class="ctsh"]/div'
        )

        for card in review_cards:
            # 提取 review_id
            link = card.xpath('.//a[contains(@href, "/review/")]/@href').get()
            if not link:
                continue
            match = re.search(r"/review/(\d+)/?", link)
            if not match:
                continue
            review_id = match.group(1)

            # 从列表页提取能拿到的元数据
            meta_item = ReviewItem()
            meta_item["movie_id"] = movie_id
            meta_item["nickname"] = self._extract(
                card,
                './/a[contains(@class, "name")]/text()',
            )
            meta_item["review_time"] = self._extract(
                card,
                './/span[contains(@class, "main-meta")]/text()',
            )
            meta_item["useful_num"] = self._extract_int(
                card,
                './/a[contains(@class, "useful")]/text()',
            )
            meta_item["useless_num"] = self._extract_int(
                card,
                './/a[contains(@class, "useless")]/text()',
            )
            meta_item["reply_num"] = self._extract_int(
                card,
                './/a[contains(text(), "回应")]/text()',
            )

            detail_url = REVIEW_DETAIL_URL.format(review_id=review_id)
            yield response.follow(
                detail_url,
                callback=self.parse_review_detail,
                meta={
                    "movie_id": movie_id,
                    "meta_item": meta_item,
                },
            )

        # 翻页
        pages_done = response.meta.get("pages_done", 0) + 1
        if self.max_pages and pages_done >= self.max_pages:
            return

        next_page = response.xpath(
            '//span[@class="next"]/a/@href | //a[contains(text(), "后页")]/@href'
        ).get()
        if next_page:
            yield response.follow(
                next_page,
                callback=self.parse_review_list,
                meta={
                    "movie_id": movie_id,
                    "start": response.meta.get("start", 0),
                    "pages_done": pages_done,
                },
            )

    def parse_review_detail(self, response):
        """影评详情页 — 提取完整内容"""
        meta_item = response.meta["meta_item"]

        # 影评正文
        content_parts = response.xpath(
            '//div[contains(@class, "review-content")]//p/text()'
        ).getall()

        meta_item["content"] = "\n".join(p.strip() for p in content_parts if p.strip())
        meta_item["share_num"] = self._extract_int(
            response,
            '//span[contains(text(), "转发")]/../text()',
        )

        yield meta_item

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
