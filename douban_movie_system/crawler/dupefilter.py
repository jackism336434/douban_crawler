"""
Redis-based dupefilter for Scrapy.

替代默认的内存去重，支持爬虫重启后恢复已抓取的 URL 集合。
不依赖 scrapy-redis 库，轻量实现。
"""

import logging

from scrapy.dupefilters import BaseDupeFilter
from scrapy.utils.request import request_fingerprint

logger = logging.getLogger(__name__)


class RedisDupeFilter(BaseDupeFilter):
    """使用 Redis Set 持久化请求指纹去重"""

    def __init__(self, server, key):
        self.server = server
        self.key = key
        self.fingerprints_seen = set()  # 本地缓存，减少 Redis 往返

    @classmethod
    def from_crawler(cls, crawler):
        try:
            import redis
        except ImportError:
            raise ImportError(
                "redis-py is required for RedisDupeFilter. "
                "Install it with: pip install redis"
            )

        host = crawler.settings.get("REDIS_HOST", "localhost")
        port = crawler.settings.getint("REDIS_PORT", 6379)
        db = crawler.settings.getint("REDIS_DB", 0)
        key_prefix = crawler.settings.get("REDIS_KEY_PREFIX", "douban_crawler:dupefilter")

        try:
            server = redis.Redis(host=host, port=port, db=db, decode_responses=True)
            server.ping()
            logger.info("RedisDupeFilter connected to %s:%d db=%d", host, port, db)
        except redis.ConnectionError as e:
            logger.error("Redis connection failed: %s. Falling back to in-memory only.", e)
            server = None

        return cls(server=server, key=f"{key_prefix}:fingerprints")

    @classmethod
    def from_settings(cls, settings):
        """Fallback: in-memory mode when Redis is unavailable"""
        return cls(server=None, key="douban_crawler:dupefilter:fingerprints")

    def request_seen(self, request):
        fp = self.request_fingerprint(request)

        # 先检查本地缓存
        if fp in self.fingerprints_seen:
            return True

        # 再检查 Redis
        if self.server:
            try:
                if self.server.sismember(self.key, fp):
                    self.fingerprints_seen.add(fp)
                    return True
            except Exception:
                pass  # Redis 异常，当作没见过

        # 记录到本地和 Redis
        self.fingerprints_seen.add(fp)
        if self.server:
            try:
                self.server.sadd(self.key, fp)
            except Exception:
                pass

        return False

    def request_fingerprint(self, request):
        return request_fingerprint(request)

    def close(self, reason):
        if self.server:
            try:
                count = self.server.scard(self.key)
                logger.info(
                    "RedisDupeFilter closed: %d fingerprints stored (key=%s)",
                    count,
                    self.key,
                )
            except Exception:
                pass

    def log(self, request, spider):
        """Scrapy 会在 request_seen 返回 False 后调用此方法，此处无需额外操作"""
        pass
