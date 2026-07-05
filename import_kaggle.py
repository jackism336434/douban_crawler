"""
从 Kaggle douban_movies_2021.json 导入数据到 MySQL。

数据源: 67,132 部电影, 389 MB JSON
目标: douban_movie 数据库 (movie, movie_person, movie_genre 三表)

运行: python import_kaggle.py
"""

import ast
import json
import re
import sys
import hashlib

import pymysql

JSON_PATH = "/home/jack/.cache/kagglehub/datasets/william18652/douban-movies/versions/1/douban_movies_2021.json"

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "crawler",
    "password": "123456",
    "database": "douban_movie",
    "charset": "utf8mb4",
}

BATCH_SIZE = 500


def join_array(arr):
    """将拆分的字符串数组合并回原始 Python 字面量字符串"""
    if not arr or not isinstance(arr, list):
        return None
    if all(isinstance(x, str) for x in arr):
        return "".join(arr)
    return None


def parse_person_list(raw_arr):
    """解析导演/编剧/演员列表 — 用正则提取 name 字段 (ast.literal_eval 因 URL 损毁而失败)"""
    text = join_array(raw_arr)
    if not text:
        return []
    # 从畸形的 Python repr 中提取 'name': 'xxx' 字段
    names = re.findall(r"'name':\s*'([^']*)'", text)
    return [(name, "") for name in names if name]


def parse_string_list(raw_arr):
    """解析字符串列表 — 修复缺失逗号后 ast.literal_eval，失败则正则提取"""
    text = join_array(raw_arr)
    if not text:
        return []
    # 修复: 相邻引号之间插入逗号 (数据序列化 bug)
    fixed = re.sub(r"'\s*'", "', '", text)
    try:
        items = ast.literal_eval(fixed)
        if isinstance(items, list):
            return [str(x).strip() for x in items if x]
    except (SyntaxError, ValueError):
        pass
    # 正则回退
    items = re.findall(r"'([^']*)'", text)
    return [x.strip() for x in items if x.strip()]


def safe_int(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def safe_float(val):
    try:
        return round(float(val), 1)
    except (TypeError, ValueError):
        return None


def import_data():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    with open(JSON_PATH) as f:
        data = json.load(f)

    total = len(data)
    print(f"Total records: {total}")

    movie_count = 0
    person_count = 0
    genre_count = 0
    movie_batch = []
    person_batch = []
    genre_batch = []

    for i, rec in enumerate(data):
        movie_id = safe_int(rec.get("movie_id"))
        if not movie_id:
            continue

        # ---- 电影基本信息 ----
        title = rec.get("title", "")
        original_title = rec.get("original_title", "")
        # 拼接: 中文名 + 英文名
        movie_name = f"{title} {original_title}".strip() if original_title else title

        rating = rec.get("rating") or {}
        score = safe_float(rating.get("score"))
        score_count = safe_int(rating.get("count"))

        images = rec.get("images") or {}
        poster_url = images.get("large", images.get("small", ""))

        summary = rec.get("summary", "")

        # 国家/语言/上映日期/片长 (取第一个)
        countries_list = parse_string_list(rec.get("countries"))
        languages_list = parse_string_list(rec.get("languages"))
        pubdates_list = parse_string_list(rec.get("pubdates"))
        durations_list = parse_string_list(rec.get("durations"))
        aka_list = parse_string_list(rec.get("aka"))

        country = " / ".join(countries_list[:3]) if countries_list else ""
        language = " / ".join(languages_list[:3]) if languages_list else ""
        release_date = pubdates_list[0] if pubdates_list else str(rec.get("year", ""))
        duration = durations_list[0] if durations_list else ""
        alias_name = " / ".join(aka_list[:5]) if aka_list else ""

        movie_batch.append({
            "movie_id": movie_id,
            "movie_name": movie_name[:255],
            "poster_url": poster_url or "",
            "intro": (summary or "")[:65535],
            "country": country[:255],
            "language": language[:255],
            "release_date": release_date[:255],
            "duration": duration[:255],
            "imdb_url": "",
            "alias_name": alias_name[:65535],
            "douban_score": score,
            "rating_count": score_count,
            "comment_count": safe_int(rec.get("comments_count")),
            "review_count": safe_int(rec.get("reviews_count")),
        })

        # ---- 人物关系 ----
        for person in parse_person_list(rec.get("directors")):
            if person[0]:
                person_batch.append((movie_id, person[0], "director"))
        for person in parse_person_list(rec.get("writers")):
            if person[0]:
                person_batch.append((movie_id, person[0], "writer"))
        for person in parse_person_list(rec.get("actors")):
            if person[0]:
                person_batch.append((movie_id, person[0], "actor"))

        # ---- 类型 ----
        for g in parse_string_list(rec.get("genres")):
            if g:
                genre_batch.append((movie_id, g))

        movie_count += 1

        # 批量写入
        if len(movie_batch) >= BATCH_SIZE:
            _flush_movies(cursor, movie_batch)
            _flush_persons(cursor, person_batch)
            _flush_genres(cursor, genre_batch)
            conn.commit()
            print(f"  Progress: {movie_count}/{total} ({movie_count*100/total:.1f}%)")
            movie_batch.clear()
            person_batch.clear()
            genre_batch.clear()

    # 最后一批
    if movie_batch:
        _flush_movies(cursor, movie_batch)
        _flush_persons(cursor, person_batch)
        _flush_genres(cursor, genre_batch)
        conn.commit()

    cursor.close()
    conn.close()

    print(f"\nDone! Imported {movie_count} movies.")
    # 统计
    conn2 = pymysql.connect(**DB_CONFIG)
    c2 = conn2.cursor()
    c2.execute("SELECT COUNT(*) FROM movie")
    print(f"movie table: {c2.fetchone()[0]} rows")
    c2.execute("SELECT COUNT(*) FROM movie_person")
    print(f"movie_person table: {c2.fetchone()[0]} rows")
    c2.execute("SELECT COUNT(*) FROM movie_genre")
    print(f"movie_genre table: {c2.fetchone()[0]} rows")
    c2.close()
    conn2.close()


MOVIE_SQL = """
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
        douban_score = VALUES(douban_score),
        rating_count = VALUES(rating_count),
        comment_count = VALUES(comment_count),
        review_count = VALUES(review_count)
"""

PERSON_SQL = """
    INSERT IGNORE INTO movie_person (movie_id, person_name, role)
    VALUES (%s, %s, %s)
"""

GENRE_SQL = """
    INSERT IGNORE INTO movie_genre (movie_id, genre_name)
    VALUES (%s, %s)
"""


def _flush_movies(cursor, batch):
    cursor.executemany(MOVIE_SQL, batch)


def _flush_persons(cursor, batch):
    cursor.executemany(PERSON_SQL, batch)


def _flush_genres(cursor, batch):
    cursor.executemany(GENRE_SQL, batch)


if __name__ == "__main__":
    import_data()
