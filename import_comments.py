"""
导入公开数据集短评到 MySQL comment 表。

数据源:
  1. CMM Kaggle comment.xlsx — 409K 条，有 movie_id
  2. GitHub Douban-Movie-Review-Dataset — 472K 条，需要 movie_name 匹配

运行: python import_comments.py
"""

import hashlib
import os
import re
import csv

import pandas as pd
import pymysql

DB_CONFIG = {
    "host": "127.0.0.1", "port": 3306,
    "user": "crawler", "password": "123456",
    "database": "douban_movie", "charset": "utf8mb4",
}

CMM_BASE = "/home/jack/.cache/kagglehub/datasets/seldonlin/cmm-chinese-multi-modal-movie/versions/1/dataset"
GITHUB_BASE = "/tmp/douban_reviews_gh"

BATCH_SIZE = 1000


def import_cmm():
    """CMM 数据集 — 409K 条短评，直接有 movie_id"""
    print("=== Importing CMM comments ===")
    df = pd.read_excel(f"{CMM_BASE}/comment.xlsx")
    print(f"  Records: {len(df)}")

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    batch = []
    total = 0

    for _, row in df.iterrows():
        movie_id = row.get("ID")
        content = str(row.get("comment", "")).strip()
        if pd.isna(movie_id) or not content:
            continue

        movie_id = int(movie_id)
        nickname = str(row.get("name", ""))[:255]  # CMM uses 'name' for username
        likes = int(row.get("number_likes", 0)) if not pd.isna(row.get("number_likes")) else 0
        date_str = str(row.get("date", ""))
        content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

        batch.append({
            "movie_id": movie_id,
            "nickname": nickname,
            "useful_num": likes,
            "content": content,
            "content_hash": content_hash,
            "comment_time": _parse_date(date_str),
        })

        if len(batch) >= BATCH_SIZE:
            _flush_comments(cursor, batch)
            conn.commit()
            total += len(batch)
            batch.clear()
            print(f"  CMM: {total}...")

    if batch:
        _flush_comments(cursor, batch)
        conn.commit()
        total += len(batch)

    cursor.close()
    conn.close()
    print(f"  CMM done: {total} imported")


def import_github():
    """GitHub 数据集 — 472K 条短评，需要 movie_name → movie_id 匹配"""
    print("=== Importing GitHub comments ===")

    # 预加载 movie_name → movie_id 映射
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT movie_id, movie_name FROM movie")
    name_to_id = {}
    for mid, mname in cursor.fetchall():
        # 标准化: 去掉英文名和特殊字符
        clean = re.sub(r"[^一-鿿]", "", mname or "")
        if clean and len(clean) >= 2:
            name_to_id[clean] = mid

    print(f"  Loaded {len(name_to_id)} movie name mappings")

    batch = []
    total = 0
    matched = 0
    unmatched = 0

    for root, dirs, files in os.walk(GITHUB_BASE):
        for fname in files:
            if not fname.endswith(".csv") or fname == "note.txt":
                continue

            # 电影名来自文件名 (去掉 .csv)
            movie_name_raw = fname.replace(".csv", "")
            clean_name = re.sub(r"[^一-鿿]", "", movie_name_raw)
            movie_id = name_to_id.get(clean_name)

            fpath = os.path.join(root, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if len(row) < 4:
                            continue
                        # Format: date, username, comment, star, sentiment, likes, score
                        date_str = row[0].strip() if len(row) > 0 else ""
                        nickname = row[1].strip()[:255] if len(row) > 1 else ""
                        content = row[2].strip() if len(row) > 2 else ""
                        likes_str = row[5].strip() if len(row) > 5 else "0"

                        if not content:
                            continue

                        likes = 0
                        try:
                            likes = int(float(likes_str))
                        except:
                            pass

                        content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

                        batch.append({
                            "movie_id": movie_id or 0,
                            "nickname": nickname,
                            "useful_num": likes,
                            "content": content[:65535],
                            "content_hash": content_hash,
                            "comment_time": _parse_date(date_str),
                        })

                        if movie_id:
                            matched += 1
                        else:
                            unmatched += 1

                        if len(batch) >= BATCH_SIZE:
                            _flush_comments(cursor, batch)
                            conn.commit()
                            total += len(batch)
                            batch.clear()
                            if total % 50000 == 0:
                                print(f"  GitHub: {total} (matched={matched}, unmatched={unmatched})")
            except Exception as e:
                pass  # skip corrupt files

    if batch:
        _flush_comments(cursor, batch)
        conn.commit()
        total += len(batch)

    cursor.close()
    conn.close()
    print(f"  GitHub done: {total} total, {matched} matched, {unmatched} unmatched")


def _flush_comments(cursor, batch):
    sql = """
        INSERT IGNORE INTO comment (movie_id, nickname, comment_time, useful_num, content, content_hash)
        VALUES (%(movie_id)s, %(nickname)s, %(comment_time)s, %(useful_num)s, %(content)s, %(content_hash)s)
    """
    cursor.executemany(sql, batch)


def _parse_date(s):
    """尝试多种日期格式解析"""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d", "%Y/%m/%d"]:
        try:
            return pd.to_datetime(s, format=fmt).to_pydatetime()
        except:
            pass
    try:
        return pd.to_datetime(s).to_pydatetime()
    except:
        return None


if __name__ == "__main__":
    import_cmm()
    import_github()

    # 统计
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM comment")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT movie_id) FROM comment")
    movies = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    print(f"\n=== Final: {total} comments across {movies} movies ===")
