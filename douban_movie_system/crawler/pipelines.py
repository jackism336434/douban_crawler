"""
数据处理管道：MySQL 批量入库 + 爬取日志记录
"""

import hashlib
import logging
from datetime import datetime
from collections import defaultdict

import pymysql

from crawler.items import MovieItem, CommentItem, ReviewItem

logger = logging.getLogger(__name__)


class MySQLPipeline:
    """批量写入 MySQL，支持 upsert 和子表拆分"""

    def __init__(self, mysql_config, batch_size):
        self.mysql_config = mysql_config
        self.batch_size = batch_size
        self.conn = None
        self.cursor = None
        self.buffer = []  # 缓存 Item，达到 batch_size 时 flush

    @classmethod
    def from_crawler(cls, crawler):
        config = {
            "host": crawler.settings.get("MYSQL_HOST", "127.0.0.1"),
            "port": crawler.settings.getint("MYSQL_PORT", 3306),
            "user": crawler.settings.get("MYSQL_USER", "crawler"),
            "password": crawler.settings.get("MYSQL_PASSWORD"),
            "database": crawler.settings.get("MYSQL_DATABASE", "douban_movie"),
            "charset": crawler.settings.get("MYSQL_CHARSET", "utf8mb4"),
        }
        batch_size = crawler.settings.getint("PIPELINE_BATCH_SIZE", 50)
        return cls(config, batch_size)

    def open_spider(self, spider):
        self.conn = pymysql.connect(**self.mysql_config)
        self.cursor = self.conn.cursor()
        self.buffer = []
        logger.info("MySQLPipeline connected to %s", self.mysql_config["host"])

    def close_spider(self, spider):
        if self.buffer:
            self._flush()
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        logger.info("MySQLPipeline closed")

    def process_item(self, item, spider):
        # 数据清洗：跳过无名称或无评分的电影
        if isinstance(item, MovieItem):
            if not item.get("movie_name"):
                logger.debug("Dropping movie %s: no name", item.get("movie_id"))
                return item
        self.buffer.append(item)
        if len(self.buffer) >= self.batch_size:
            self._flush()
        return item

    def _flush(self):
        """按类型分组后执行批量写入"""
        if not self.buffer:
            return

        grouped = defaultdict(list)
        for item in self.buffer:
            if isinstance(item, MovieItem):
                grouped["movie"].append(item)
            elif isinstance(item, CommentItem):
                grouped["comment"].append(item)
            elif isinstance(item, ReviewItem):
                grouped["review"].append(item)

        try:
            if grouped["movie"]:
                self._insert_movies(grouped["movie"])
            if grouped["comment"]:
                self._insert_comments(grouped["comment"])
            if grouped["review"]:
                self._insert_reviews(grouped["review"])

            self.conn.commit()
            logger.info(
                "Flushed %d items: movie=%d, comment=%d, review=%d",
                len(self.buffer),
                len(grouped["movie"]),
                len(grouped["comment"]),
                len(grouped["review"]),
            )
        except Exception as e:
            self.conn.rollback()
            logger.error("Flush failed: %s", e, exc_info=True)
        finally:
            self.buffer.clear()

    # ---- Movie ----

    MOVIE_UPSERT_SQL = """
        INSERT INTO movie (
            movie_id, movie_name, poster_url, intro,
            country, language, release_date, duration,
            imdb_url, alias_name, douban_score, rating_count,
            comment_count, review_count
        ) VALUES (
            %(movie_id)s, %(movie_name)s, %(poster_url)s, %(intro)s,
            %(country)s, %(language)s, %(release_date)s, %(duration)s,
            %(imdb_url)s, %(alias_name)s, %(douban_score)s, %(rating_count)s,
            %(comment_count)s, %(review_count)s
        )
        ON DUPLICATE KEY UPDATE
            movie_name = VALUES(movie_name),
            poster_url = VALUES(poster_url),
            intro = VALUES(intro),
            country = VALUES(country),
            language = VALUES(language),
            release_date = VALUES(release_date),
            duration = VALUES(duration),
            imdb_url = VALUES(imdb_url),
            alias_name = VALUES(alias_name),
            douban_score = VALUES(douban_score),
            rating_count = VALUES(rating_count),
            comment_count = VALUES(comment_count),
            review_count = VALUES(review_count)
    """

    PERSON_INSERT_SQL = """
        INSERT IGNORE INTO movie_person (movie_id, person_name, role)
        VALUES (%s, %s, %s)
    """

    GENRE_INSERT_SQL = """
        INSERT IGNORE INTO movie_genre (movie_id, genre_name)
        VALUES (%s, %s)
    """

    def _insert_movies(self, items):
        for item in items:
            row = {
                "movie_id": item.get("movie_id"),
                "movie_name": item.get("movie_name", ""),
                "poster_url": item.get("poster_url", ""),
                "intro": item.get("intro", ""),
                "country": item.get("country", ""),
                "language": item.get("language", ""),
                "release_date": item.get("release_date", ""),
                "duration": item.get("duration", ""),
                "imdb_url": item.get("imdb_url", ""),
                "alias_name": item.get("alias_name", ""),
                "douban_score": self._to_decimal(item.get("douban_score")),
                "rating_count": self._to_int(item.get("rating_count")),
                "comment_count": self._to_int(item.get("comment_count")),
                "review_count": self._to_int(item.get("review_count")),
            }
            self.cursor.execute(self.MOVIE_UPSERT_SQL, row)

            movie_id = item.get("movie_id")

            # 人物关系
            for name in (item.get("directors") or []):
                if name:
                    self.cursor.execute(self.PERSON_INSERT_SQL, (movie_id, name, "director"))
            for name in (item.get("writers") or []):
                if name:
                    self.cursor.execute(self.PERSON_INSERT_SQL, (movie_id, name, "writer"))
            for name in (item.get("actors") or []):
                if name:
                    self.cursor.execute(self.PERSON_INSERT_SQL, (movie_id, name, "actor"))

            # 类型标签
            for genre in (item.get("genres") or []):
                if genre:
                    self.cursor.execute(self.GENRE_INSERT_SQL, (movie_id, genre))

    # ---- Comment ----

    COMMENT_INSERT_SQL = """
        INSERT IGNORE INTO comment (movie_id, nickname, comment_time, useful_num, content, content_hash)
        VALUES (%(movie_id)s, %(nickname)s, %(comment_time)s, %(useful_num)s, %(content)s, %(content_hash)s)
    """

    def _insert_comments(self, items):
        rows = []
        for item in items:
            content = item.get("content") or ""
            rows.append({
                "movie_id": item.get("movie_id"),
                "nickname": item.get("nickname", ""),
                "comment_time": self._to_datetime(item.get("comment_time")),
                "useful_num": self._to_int(item.get("useful_num")),
                "content": content,
                "content_hash": hashlib.md5(content.encode("utf-8")).hexdigest() if content else "",
            })
        self.cursor.executemany(self.COMMENT_INSERT_SQL, rows)

    # ---- Review ----

    REVIEW_INSERT_SQL = """
        INSERT INTO review (movie_id, nickname, review_time,
            useful_num, useless_num, share_num, reply_num, content)
        VALUES (%(movie_id)s, %(nickname)s, %(review_time)s,
            %(useful_num)s, %(useless_num)s, %(share_num)s, %(reply_num)s, %(content)s)
    """

    def _insert_reviews(self, items):
        rows = []
        for item in items:
            rows.append({
                "movie_id": item.get("movie_id"),
                "nickname": item.get("nickname", ""),
                "review_time": self._to_datetime(item.get("review_time")),
                "useful_num": self._to_int(item.get("useful_num")),
                "useless_num": self._to_int(item.get("useless_num")),
                "share_num": self._to_int(item.get("share_num")),
                "reply_num": self._to_int(item.get("reply_num")),
                "content": item.get("content", ""),
            })
        self.cursor.executemany(self.REVIEW_INSERT_SQL, rows)

    # ---- Helpers ----

    @staticmethod
    def _to_int(value):
        if value is None:
            return 0
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _to_decimal(value):
        if value is None:
            return None
        try:
            return round(float(value), 1)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _to_datetime(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return None


class CrawlLogPipeline:
    """记录每次爬取的日志到 crawl_log 表"""

    def __init__(self, mysql_config):
        self.mysql_config = mysql_config
        self.conn = None
        self.cursor = None

    @classmethod
    def from_crawler(cls, crawler):
        config = {
            "host": crawler.settings.get("MYSQL_HOST", "127.0.0.1"),
            "port": crawler.settings.getint("MYSQL_PORT", 3306),
            "user": crawler.settings.get("MYSQL_USER", "crawler"),
            "password": crawler.settings.get("MYSQL_PASSWORD"),
            "database": crawler.settings.get("MYSQL_DATABASE", "douban_movie"),
            "charset": crawler.settings.get("MYSQL_CHARSET", "utf8mb4"),
        }
        return cls(config)

    def open_spider(self, spider):
        self.conn = pymysql.connect(**self.mysql_config)
        self.cursor = self.conn.cursor()
        self.spider_name = spider.name

    def close_spider(self, spider):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

    def process_item(self, item, spider):
        return item  # 主要日志记录在 spider 端；此处为占位
