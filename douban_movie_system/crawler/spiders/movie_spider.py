"""
电影信息爬虫：从 Top250 出发，通过推荐链式扩展。

运行方式:
    scrapy crawl movie                          # 默认: 爬取 10000 部
    scrapy crawl movie -a max_movies=20000       # 发现 20000 部(含失败的)
    scrapy crawl movie -a max_depth=2            # 限制推荐链深度
    scrapy crawl movie -a test=1                 # 测试: 5 部
"""

import re
import logging

import scrapy

from crawler.items import MovieItem

logger = logging.getLogger(__name__)

TOP250_URL = "https://movie.douban.com/top250?start={start}&filter="


class MovieSpider(scrapy.Spider):
    name = "movie"
    allowed_domains = ["movie.douban.com", "douban.com"]

    def __init__(self, max_movies=None, max_depth=None, test=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # max_movies: 成功抓取的目标数 (默认 10000)
        self.target_count = int(max_movies) if max_movies else 10000
        self.max_depth = int(max_depth) if max_depth else 3
        self.test_mode = test is not None
        self.discovered = 0   # 已发现(已调度)的电影数
        self.scraped = 0      # 成功抓取的电影数
        self.seen_ids = set()

    def start_requests(self):
        # 从 MySQL 加载已成功抓取的 movie_id，跳过重复
        self._load_scraped_ids()

        if self.test_mode:
            self.target_count = 5
            self.max_depth = 1
            yield scrapy.Request(
                TOP250_URL.format(start=0),
                callback=self.parse_top250,
                dont_filter=True,
            )
            return

        logger.info(
            "Starting: target=%d, max_depth=%d, already_scraped=%d",
            self.target_count, self.max_depth, len(self.seen_ids),
        )

        for start in range(0, 250, 25):
            yield scrapy.Request(
                TOP250_URL.format(start=start),
                callback=self.parse_top250,
                dont_filter=True,
            )

    def _load_scraped_ids(self):
        """从 MySQL 加载已抓取 movie_id，避免重复"""
        try:
            import pymysql
            conn = pymysql.connect(
                host="127.0.0.1", port=3306, user="crawler", password="123456",
                database="douban_movie", charset="utf8mb4",
            )
            cursor = conn.cursor()
            cursor.execute("SELECT movie_id FROM movie")
            ids = {row[0] for row in cursor.fetchall()}
            self.seen_ids.update(ids)
            cursor.close()
            conn.close()
            logger.info("Loaded %d already-scraped movie IDs from MySQL", len(ids))
        except Exception as e:
            logger.warning("Failed to load scraped IDs from MySQL: %s", e)

    # ---- 列表页 ----

    def parse_top250(self, response):
        links = response.xpath(
            '//div[@class="hd"]/a[contains(@href, "/subject/")]/@href'
        ).getall()

        for link in links:
            if self.scraped >= self.target_count:
                return
            yield from self._schedule_detail(response, link, depth=1)

        next_page = response.xpath('//span[@class="next"]/a/@href').get()
        if next_page and self.scraped < self.target_count:
            yield response.follow(next_page, callback=self.parse_top250)

    # ---- 详情页 ----

    def parse_movie_detail(self, response):
        movie_id = response.meta["movie_id"]
        depth = response.meta.get("depth", 1)

        item = self._extract_movie(response, movie_id)
        if item.get("movie_name"):
            self.scraped += 1
            if self.scraped % 100 == 0:
                logger.info(
                    "Scraped: %d/%d (depth=%d)",
                    self.scraped, self.target_count, depth,
                )
            yield item

        # 链式发现推荐电影
        if depth < self.max_depth and self.scraped < self.target_count:
            rec_links = response.xpath(
                '//div[@class="recommendations-bd"]'
                '//a[contains(@href, "/subject/")]/@href'
            ).getall()

            for link in rec_links:
                if self.scraped >= self.target_count:
                    return
                yield from self._schedule_detail(response, link, depth=depth + 1)

    # ---- 调度 ----

    def _schedule_detail(self, response, url, depth=1):
        match = re.search(r"/subject/(\d+)/?", url)
        if not match:
            return []
        movie_id = int(match.group(1))
        if movie_id in self.seen_ids:
            return []
        self.seen_ids.add(movie_id)
        self.discovered += 1

        return [
            response.follow(
                url,
                callback=self.parse_movie_detail,
                meta={"movie_id": movie_id, "depth": depth},
                errback=self._handle_error,
            )
        ]

    def _handle_error(self, failure):
        # 静默跳过失败的请求，不影响整体进度
        pass

    # ---- 字段提取 ----

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

    # ---- Helpers ----

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
