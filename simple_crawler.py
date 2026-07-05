"""
简易爬虫：逐个请求 + 长间隔，真正从豆瓣网页抓取短评和影评。
每次只请求一个页面，间隔 20-60 秒，模拟人类浏览行为。

用法:
    python simple_crawler.py    # 爬 50 部热门电影的短评和影评
"""

import re
import hashlib
import time
import random
import logging
import sys
from datetime import datetime

import requests
import pymysql
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": "127.0.0.1", "port": 3306,
    "user": "crawler", "password": "123456",
    "database": "douban_movie", "charset": "utf8mb4",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://movie.douban.com/",
}

COOKIES = {
    "dbcl2": "270218201:Em06PxOdhQU",
    "ck": "06no",
    "bid": "qewHzLB6pyg",
}

COMMENT_URL = "https://movie.douban.com/subject/{movie_id}/comments?start={start}&limit=20&status=P&sort=new_score"
REVIEW_URL = "https://movie.douban.com/subject/{movie_id}/reviews"
REVIEW_DETAIL_URL = "https://movie.douban.com/review/{review_id}/"

session = requests.Session()
session.headers.update(HEADERS)
for k, v in COOKIES.items():
    session.cookies.set(k, v)


def get_movie_ids(limit=50):
    """获取热门电影 ID 列表"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT movie_id FROM movie ORDER BY rating_count DESC LIMIT %s", (limit,))
    ids = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return ids


def crawl_comments(movie_id, max_pages=2):
    """抓取一部电影的短评"""
    crawled = 0
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    for page in range(max_pages):
        start = page * 20
        url = COMMENT_URL.format(movie_id=movie_id, start=start)

        # 随机延迟 20-40 秒
        delay = random.uniform(20, 40)
        logger.info("  Sleeping %.1fs before comment page %d...", delay, page + 1)
        time.sleep(delay)

        try:
            r = session.get(url, timeout=15)
            if r.status_code != 200:
                logger.warning("  Comment page %d: HTTP %d", page + 1, r.status_code)
                # 检测是否被封
                if b"sec.douban.com" in r.content or r.status_code in (302, 403):
                    logger.error("  BLOCKED by Douban! Stopping.")
                    conn.close()
                    return crawled
                break

            soup = BeautifulSoup(r.text, "html.parser")
            items = soup.find_all("div", class_="comment-item")
            if not items:
                break

            for item in items:
                content_el = item.find("span", class_="short")
                if not content_el:
                    continue
                content = content_el.get_text(strip=True)
                if not content:
                    continue

                nickname_el = item.find("span", class_="comment-info").find("a") if item.find("span", class_="comment-info") else None
                nickname = nickname_el.get_text(strip=True) if nickname_el else ""
                time_el = item.find("span", class_="comment-time")
                comment_time = time_el.get("title", "") if time_el else ""
                votes_el = item.find("span", class_="votes")
                useful = int(re.search(r"\d+", votes_el.get_text(strip=True)).group()) if votes_el else 0

                content_hash = hashlib.md5(content.encode()).hexdigest()

                cursor.execute(
                    """INSERT IGNORE INTO comment (movie_id, nickname, comment_time, useful_num, content, content_hash)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (movie_id, nickname, _parse_date(comment_time), useful, content, content_hash),
                )
                crawled += 1

            conn.commit()
            logger.info("  Comment page %d: %d items scraped", page + 1, len(items))

        except Exception as e:
            logger.error("  Comment page %d error: %s", page + 1, e)
            break

    cursor.close()
    conn.close()
    return crawled


def crawl_reviews(movie_id, max_pages=1):
    """抓取一部电影的影评"""
    crawled = 0
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # 先抓影评列表页
    url = REVIEW_URL.format(movie_id=movie_id)
    delay = random.uniform(20, 40)
    logger.info("  Sleeping %.1fs before review list...", delay)
    time.sleep(delay)

    try:
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            logger.warning("  Review list: HTTP %d", r.status_code)
            if b"sec.douban.com" in r.content or r.status_code in (302, 403):
                logger.error("  BLOCKED! Stopping.")
                conn.close()
                return crawled
            conn.close()
            return crawled

        soup = BeautifulSoup(r.text, "html.parser")
        # 提取影评链接
        review_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = re.search(r"/review/(\d+)/?", href)
            if m:
                review_links.append(m.group(1))

        review_links = list(set(review_links))  # 去重
        logger.info("  Found %d review links", len(review_links))

        # 逐个抓影评详情
        for review_id in review_links[:10]:  # 每部最多10篇
            detail_url = REVIEW_DETAIL_URL.format(review_id=review_id)
            delay = random.uniform(15, 30)
            time.sleep(delay)

            try:
                r2 = session.get(detail_url, timeout=15)
                if r2.status_code != 200:
                    continue

                soup2 = BeautifulSoup(r2.text, "html.parser")

                # 提取影评内容
                content_div = soup2.find("div", class_="review-content")
                if not content_div:
                    continue
                paragraphs = content_div.find_all("p")
                content = "\n".join(p.get_text(strip=True) for p in paragraphs)
                if not content or len(content) < 50:
                    continue

                # 影评元数据
                header = soup2.find("header", class_="main-hd")
                nickname = ""
                review_time = ""
                if header:
                    name_el = header.find("a", class_="name")
                    nickname = name_el.get_text(strip=True) if name_el else ""
                    time_el = header.find("span", class_="main-meta")
                    review_time = time_el.get_text(strip=True) if time_el else ""

                # 有用/无用
                useful_btn = soup2.find("button", class_=lambda c: c and "useful" in c)
                useless_btn = soup2.find("button", class_=lambda c: c and "useless" in c)
                useful = int(re.search(r"\d+", useful_btn.get_text()).group()) if useful_btn else 0
                useless = int(re.search(r"\d+", useless_btn.get_text()).group()) if useless_btn else 0

                cursor.execute(
                    """INSERT INTO review (movie_id, nickname, review_time, useful_num, useless_num, content)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (movie_id, nickname, _parse_date(review_time), useful, useless, content),
                )
                conn.commit()
                crawled += 1
                logger.info("    Review %s: %d chars by %s", review_id, len(content), nickname)

            except Exception as e:
                logger.warning("    Review %s error: %s", review_id, e)
                continue

    except Exception as e:
        logger.error("  Review list error: %s", e)

    cursor.close()
    conn.close()
    return crawled


def _parse_date(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"]:
        try:
            return datetime.strptime(s, fmt)
        except:
            pass
    return None


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    movie_ids = get_movie_ids(limit)
    logger.info("Starting crawl: %d movies", len(movie_ids))

    total_comments = 0
    total_reviews = 0
    blocked = False

    for i, mid in enumerate(movie_ids):
        if blocked:
            break

        # 电影间延迟 40-80 秒
        if i > 0:
            delay = random.uniform(40, 80)
            logger.info("Inter-movie delay: %.1fs", delay)
            time.sleep(delay)

        logger.info("[%d/%d] Movie %d", i + 1, len(movie_ids), mid)

        # 爬短评
        c = crawl_comments(mid, max_pages=2)
        if c == 0 and total_comments > 0:
            # 可能被封了
            pass
        total_comments += c

        # 爬影评
        r = crawl_reviews(mid, max_pages=1)
        total_reviews += r

        logger.info("  Totals: %d comments, %d reviews scraped so far", total_comments, total_reviews)

        # 每小时最多爬 10 部
        if (i + 1) % 10 == 0:
            logger.info("  === Cooldown 10 minutes ===")
            time.sleep(600)

    # 最终统计
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM comment")
    final_c = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM review")
    final_r = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    logger.info("=" * 50)
    logger.info("Crawl complete!")
    logger.info("  This session: %d comments, %d reviews scraped", total_comments, total_reviews)
    logger.info("  Comment table total: %d", final_c)
    logger.info("  Review table total: %d", final_r)
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
