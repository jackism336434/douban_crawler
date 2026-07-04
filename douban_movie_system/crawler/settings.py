BOT_NAME = "crawler"

SPIDER_MODULES = ["crawler.spiders"]
NEWSPIDER_MODULE = "crawler.spiders"

# ============================================================
# Anti-Crawl & Politeness
# ============================================================
DOWNLOAD_DELAY = 3.0                    # 请求间隔（秒）
CONCURRENT_REQUESTS = 8                 # 全局并发数
CONCURRENT_REQUESTS_PER_DOMAIN = 4     # 单域名并发数
CONCURRENT_REQUESTS_PER_IP = 4         # 单IP并发数

ROBOTSTXT_OBEY = False                  # 豆瓣 robots.txt 限制较多，关闭

DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

COOKIES_ENABLED = True

# ============================================================
# AutoThrottle — 自适应限速 (主要反爬机制)
# ============================================================
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 3           # 初始延迟
AUTOTHROTTLE_MAX_DELAY = 30            # 最大延迟
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0  # 目标并发度

# ============================================================
# Retry — 失败重试
# ============================================================
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [403, 429, 500, 502, 503, 504]

# ============================================================
# Redis — 持久化去重
# ============================================================
DUPEFILTER_CLASS = "crawler.dupefilter.RedisDupeFilter"
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_KEY_PREFIX = "douban_crawler:dupefilter"

# ============================================================
# MySQL — 数据库连接
# ============================================================
MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = 3306
MYSQL_USER = "crawler"
MYSQL_PASSWORD = "123456"
MYSQL_DATABASE = "douban_movie"
MYSQL_CHARSET = "utf8mb4"

# ============================================================
# Pipeline — 数据处理管道
# ============================================================
ITEM_PIPELINES = {
    "crawler.pipelines.MySQLPipeline": 300,
    "crawler.pipelines.CrawlLogPipeline": 400,
}
PIPELINE_BATCH_SIZE = 50  # 批量插入大小

# ============================================================
# Downloader Middlewares — 反爬中间件
# ============================================================
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,  # 禁用默认UA
    "crawler.middlewares.CookieInjectMiddleware": 100,   # 优先注入 Cookie
    "crawler.middlewares.RandomUserAgentMiddleware": 400,
    "crawler.middlewares.DoubanChallengeMiddleware": 410,
}

# 豆瓣登录 Cookie (从浏览器复制，绕过反爬)
# 格式: "key1=val1; key2=val2; ..."
COOKIE_STRING = ""

# ============================================================
# Misc
# ============================================================
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"

# 日志
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
