"""
电影信息爬虫：从豆瓣榜单/搜索接口获取电影列表，抓取详情页。

运行方式:
    scrapy crawl movie                              # 默认: top250 + 各分类
    scrapy crawl movie -a max_movies=100            # 限制电影数量
    scrapy crawl movie -a test=1                    # 测试模式: 只爬 Top250 首页 (~25部)
"""

import re
import json
import logging

import scrapy

from crawler.items import MovieItem

logger = logging.getLogger(__name__)

# 豆瓣电影搜索 API (JSON 接口，无需 JS 渲染)
SEARCH_API = (
    "https://movie.douban.com/j/new_search_subjects"
    "?sort=U&range=0,10&tags={tag}&start={start}&limit=20"
)

# 种子: 各类型标签
SEED_TAGS = [
    "",          # 全部(按热度)
    "电影",       # 过滤电视剧
    "剧情",
    "喜剧",
    "动作",
    "爱情",
    "科幻",
    "悬疑",
    "动画",
    "纪录片",
]

# 豆瓣电影 Top250 (服务端渲染)
TOP250_URL = "https://movie.douban.com/top250?start={start}&filter="

BASE_SUBJECT_URL = "https://movie.douban.com/subject/{movie_id}/"


class MovieSpider(scrapy.Spider):
    name = "movie"
    allowed_domains = ["movie.douban.com", "douban.com"]

    def __init__(self, max_movies=None, start_page=None, end_page=None, test=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_movies = int(max_movies) if max_movies else None
        self.start_page = int(start_page) if start_page else 0
        self.end_page = int(end_page) if end_page else None
        self.test_mode = test is not None  # -a test=1 启用测试模式
        self.movie_count = 0
        self.seen_ids = set()

    def start_requests(self):
        """从多个种子源启动"""

        # 测试模式：仅 Top250 首页
        if self.test_mode:
            self.max_movies = self.max_movies or 5  # 测试默认只爬5部
            yield scrapy.Request(
                TOP250_URL.format(start=0),
                callback=self.parse_top250,
                dont_filter=True,
            )
            return

        # 源1: Top250 列表 (服务端渲染)
        for start in range(0, 250, 25):
            yield scrapy.Request(
                TOP250_URL.format(start=start),
                callback=self.parse_top250,
                dont_filter=True,
            )

        # 源2: 搜索 API (JSON)
        for tag in SEED_TAGS:
            for start in range(0, 200, 20):  # 每个标签取10页
                if self.end_page and start // 20 > self.end_page:
                    break
                url = SEARCH_API.format(tag=tag, start=start)
                yield scrapy.Request(
                    url,
                    callback=self.parse_search_api,
                    meta={"tag": tag},
                )

    def parse_top250(self, response):
        """Top250 列表页 — 提取电影链接"""
        links = response.xpath(
            '//div[@class="hd"]/a[contains(@href, "/subject/")]/@href'
        ).getall()

        for link in links:
            if self._hit_limit():
                return
            yield from self._follow_detail(response, link, source="top250")

        # 翻页 (Top250 共10页)
        next_page = response.xpath('//span[@class="next"]/a/@href').get()
        if next_page:
            yield response.follow(next_page, callback=self.parse_top250)

    def parse_search_api(self, response):
        """搜索 API — JSON 响应，提取电影 ID"""
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            logger.warning("Failed to decode JSON from: %s", response.url)
            return

        subjects = data.get("data", [])
        for subject in subjects:
            if self._hit_limit():
                return
            movie_id = subject.get("id")
            if movie_id and movie_id not in self.seen_ids:
                url = BASE_SUBJECT_URL.format(movie_id=movie_id)
                yield from self._follow_detail(response, url, source="search_api")

    def _follow_detail(self, response, url, source="unknown"):
        """跟进电影详情页"""
        match = re.search(r"/subject/(\d+)/?", url)
        if not match:
            return []
        movie_id = int(match.group(1))
        if movie_id in self.seen_ids:
            return []
        self.seen_ids.add(movie_id)

        self.movie_count += 1
        return [
            response.follow(
                url,
                callback=self.parse_movie_detail,
                meta={"movie_id": movie_id, "source": source},
                errback=self._handle_error,
            )
        ]

    def _hit_limit(self):
        return self.max_movies and self.movie_count >= self.max_movies

    def _handle_error(self, failure):
        logger.error("Request failed: %s", failure.request.url)

    # ---- 详情页解析 ----

    def parse_movie_detail(self, response):
        """电影详情页 — 提取所有字段"""
        movie_id = response.meta["movie_id"]

        item = MovieItem()
        item["movie_id"] = movie_id

        # 电影名称
        item["movie_name"] = self._extract_one(
            response, '//span[@property="v:itemreviewed"]/text()'
        ) or self._extract_one(response, '//title/text()')

        # 海报
        item["poster_url"] = self._extract_one(
            response, '//img[@rel="v:image"]/@src'
        )

        # 剧情简介
        item["intro"] = self._extract_one(
            response, '//span[@property="v:summary"]/text()'
        )

        # 导演 / 编剧 / 主演
        item["directors"] = response.xpath(
            '//a[@rel="v:directedBy"]/text()'
        ).getall()
        item["writers"] = self._extract_person_list(response, "编剧")
        item["actors"] = response.xpath(
            '//a[@rel="v:starring"]/text()'
        ).getall()[:5]

        # 类型
        item["genres"] = response.xpath(
            '//span[@property="v:genre"]/text()'
        ).getall()

        # 从 #info 区域解析字段
        info_text = "".join(
            response.xpath('//div[@id="info"]//text()').getall()
        )
        if info_text:
            item["country"] = self._re_field(info_text, r"制片国家/地区:\s*(.+?)(?:\n|$)")
            item["language"] = self._re_field(info_text, r"语言:\s*(.+?)(?:\n|$)")
            item["release_date"] = self._re_field(info_text, r"上映日期:\s*(.+?)(?:\n|$)")
            item["duration"] = self._re_field(info_text, r"片长:\s*(.+?)(?:\n|$)")
            item["imdb_url"] = self._re_field(info_text, r"IMDb:\s*(.+?)(?:\n|$)")
            item["alias_name"] = self._re_field(info_text, r"又名:\s*(.+?)(?:\n|$)")

        # 评分 & 评价人数
        item["douban_score"] = self._extract_one(
            response, '//strong[@property="v:average"]/text()'
        )
        item["rating_count"] = self._extract_int(
            response, '//span[@property="v:votes"]/text()'
        )

        # 短评 / 影评计数
        item["comment_count"] = self._extract_int(
            response,
            '//div[@id="comments-section"]//span[@class="pl"]/a/text()',
            '//a[contains(@href, "comments")]//span[@class="pl"]/text()',
        )
        item["review_count"] = self._extract_int(
            response,
            '//section[contains(@class, "review")]//span[@class="pl"]/a/text()',
            '//a[contains(@href, "reviews")]//span[@class="pl"]/text()',
        )

        logger.debug("Parsed movie: %s (%s)", item["movie_name"], movie_id)
        yield item

    # ---- Helpers ----

    def _extract_one(self, selector, *xpaths):
        for xpath in xpaths:
            val = selector.xpath(xpath).get()
            if val:
                return val.strip()
        return ""

    def _extract_int(self, selector, *xpaths):
        val = self._extract_one(selector, *xpaths)
        if val:
            match = re.search(r"\d+", val.replace(",", ""))
            if match:
                return int(match.group())
        return 0

    def _extract_person_list(self, selector, role_label):
        names = selector.xpath(
            f'//span[contains(text(), "{role_label}")]'
            '/following-sibling::span[1]//a[contains(@href, "/celebrity/")]/text()'
        ).getall()
        return [n.strip() for n in names if n.strip()]

    def _re_field(self, text, pattern):
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
        return ""
