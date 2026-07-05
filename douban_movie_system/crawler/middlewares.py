import hashlib
import random
import re
import logging

from scrapy import signals, Request, FormRequest
from scrapy.exceptions import IgnoreRequest

logger = logging.getLogger(__name__)


USER_AGENTS = [
    # Googlebot — 绕过豆瓣 JS 挑战
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    # Bingbot
    "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    # Chrome macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    # Firefox Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    # Edge Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
]


class RandomUserAgentMiddleware:
    """每次请求随机选择一个 User-Agent"""

    def process_request(self, request, spider):
        ua = random.choice(USER_AGENTS)
        request.headers["User-Agent"] = ua


class CookieInjectMiddleware:
    """
    注入预设 Cookie（从 settings.COOKIE_STRING 读取）。

    在 settings.py 中配置:
        COOKIE_STRING = "key1=val1; key2=val2; ..."
    """

    def __init__(self, cookie_string):
        self.cookies = {}
        if cookie_string:
            for part in cookie_string.split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    self.cookies[k.strip()] = v.strip()

    @classmethod
    def from_crawler(cls, crawler):
        cookie_string = crawler.settings.get("COOKIE_STRING", "")
        return cls(cookie_string)

    def process_request(self, request, spider):
        if self.cookies:
            # 合并到 request.cookies (Scrapy CookiesMiddleware 会处理)
            for k, v in self.cookies.items():
                request.cookies.setdefault(k, v)


class SecDoubanRedirectMiddleware:
    """
    拦截重定向到 sec.douban.com（豆瓣反爬安全系统）。

    当豆瓣检测到爬虫行为时，会 302 重定向到 sec.douban.com。
    本中间件在 RedirectMiddleware 之前拦截这个重定向，
    不跟进而是重试原始请求。
    """

    def process_response(self, request, response, spider):
        # 检测 302/301 重定向到 sec.douban.com
        if response.status in (301, 302, 307):
            location = response.headers.get("Location", b"").decode(errors="replace")
            if "sec.douban.com" in location:
                spider.logger.warning(
                    "Blocked by sec.douban.com for %s — will retry after delay",
                    request.url,
                )
                # 返回新请求（不跟进重定向），Scrapy 会重新调度
                retry_req = request.replace(dont_filter=True)
                retry_req.meta["sec_retry_count"] = (
                    request.meta.get("sec_retry_count", 0) + 1
                )
                # 最多重试3次，超过则放弃
                if retry_req.meta["sec_retry_count"] > 3:
                    spider.logger.error(
                        "Giving up on %s after %d sec retries",
                        request.url,
                        retry_req.meta["sec_retry_count"],
                    )
                    raise IgnoreRequest("Blocked by sec.douban.com too many times")
                return retry_req

        return response


class DoubanChallengeMiddleware:
    """
    自动解决豆瓣 JS 反爬挑战页面 (SHA-512 Proof-of-Work)。

    豆瓣会对未验证的 IP 返回挑战页面，包含:
      - tok: 会话 token
      - cha: 挑战字符串
      - red: 重定向 URL

    挑战要求找到 nonce 使 SHA-512(cha + nonce) 以 "0000" 开头。
    """

    CHALLENGE_MARKER = b'id="sec"'
    CHALLENGE_URL = "https://movie.douban.com/c"

    def process_response(self, request, response, spider):
        # 检测是否为挑战页面
        if response.status == 200 and self.CHALLENGE_MARKER in response.body:
            logger.info("Douban challenge detected for %s, solving...", request.url)

            # 提取参数
            tok = self._extract_input(response, "tok")
            cha = self._extract_input(response, "cha")
            red = self._extract_input(response, "red")

            if not tok or not cha:
                logger.error("Failed to extract challenge params from %s", request.url)
                return response

            logger.info("Challenge params: tok=%s..., cha=%s...", tok[:20], cha[:20])

            # 计算 PoW
            try:
                nonce, sol = self._solve_pow(cha)
                logger.info("PoW solved: nonce=%d", nonce)
            except Exception as e:
                logger.error("PoW solve failed: %s", e)
                return response

            # 提交挑战表单
            return FormRequest(
                url=self.CHALLENGE_URL,
                formdata={"tok": tok, "cha": cha, "sol": sol, "red": red},
                callback=lambda r: self._after_challenge(r, request),
                meta={"original_request": request},
                dont_filter=True,
            )

        return response

    def _after_challenge(self, response, original_request):
        """挑战提交后，用获取的 cookie 重试原始请求"""
        if response.status == 200 and b"window.location" in response.body:
            logger.info("Challenge passed, retrying original request")
            # 从 FormRequest 自动继承的 cookies 会传递
            new_req = original_request.replace(dont_filter=True)
            return new_req

        logger.warning("Challenge submission returned status %d", response.status)
        return original_request

    @staticmethod
    def _extract_input(response, name):
        """从 HTML 中提取 hidden input 的值"""
        pattern = f'name="{name}"[^>]*value="([^"]*)"'.encode()
        match = re.search(pattern, response.body)
        if match:
            return match.group(1).decode()
        return None

    @staticmethod
    def _solve_pow(cha, difficulty=4):
        """
        计算 SHA-512 Proof-of-Work nonce。
        返回 (nonce, sol_string)。
        """
        target_prefix = "0" * difficulty
        nonce = 0
        while True:
            sol = str(nonce)
            h = hashlib.sha512((cha + sol).encode()).hexdigest()
            if h.startswith(target_prefix):
                return nonce, sol
            nonce += 1
            if nonce % 100000 == 0:
                logger.debug("PoW progress: tried %d nonces...", nonce)


# ---- 以下为 Scrapy 默认生成模板 (保留以备后续扩展) ----


class CrawlerSpiderMiddleware:
    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        return None

    def process_spider_output(self, response, result, spider):
        for i in result:
            yield i

    def process_spider_exception(self, response, exception, spider):
        pass

    def process_start_requests(self, start_requests, spider):
        for r in start_requests:
            yield r

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s", spider.name)


class CrawlerDownloaderMiddleware:
    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request, spider):
        return None

    def process_response(self, request, response, spider):
        return response

    def process_exception(self, request, exception, spider):
        pass

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s", spider.name)
