"""
导入短评数据 — v2: 先补全缺失的电影元数据，再导评论。

数据源:
  1. CMM allData.xlsx — 678 部电影基本信息
  2. CMM data.xlsx — 706 部电影基本信息
  3. CMM comment.xlsx — 409K 条短评 (有 movie_id)
  4. GitHub CSV — 472K 条短评 (有 movie_name)

运行: python import_comments_v2.py
"""

import hashlib, os, re, csv, ast
import pandas as pd
import pymysql

DB_CONFIG = {
    "host": "127.0.0.1", "port": 3306,
    "user": "crawler", "password": "123456",
    "database": "douban_movie", "charset": "utf8mb4",
}

CMM_BASE = "/home/jack/.cache/kagglehub/datasets/seldonlin/cmm-chinese-multi-modal-movie/versions/1/dataset"
GITHUB_BASE = "/tmp/douban_reviews_gh"
BATCH = 1000


def import_cmm_movies():
    """从 CMM data.xlsx 和 allData.xlsx 导入缺失的电影"""
    print("=== Importing CMM movies ===")

    movies = {}  # movie_id -> dict

    # allData.xlsx
    try:
        df = pd.read_excel(f"{CMM_BASE}/allData.xlsx")
        for _, row in df.iterrows():
            mid = int(row["id"]) if not pd.isna(row.get("id")) else None
            if not mid:
                continue
            movies[mid] = {
                "movie_id": mid,
                "movie_name": str(row.get("name", ""))[:255],
                "intro": str(row.get("introduction", ""))[:65535] if not pd.isna(row.get("introduction")) else "",
                "release_date": str(row.get("release_date", ""))[:255] if not pd.isna(row.get("release_date")) else "",
            }
    except Exception as e:
        print(f"  allData.xlsx: {e}")

    # data.xlsx
    try:
        df2 = pd.read_excel(f"{CMM_BASE}/data.xlsx")
        for _, row in df2.iterrows():
            mid = int(row["id"]) if not pd.isna(row.get("id")) else None
            if not mid:
                continue
            if mid not in movies:
                movies[mid] = {
                    "movie_id": mid,
                    "movie_name": str(row.get("name", ""))[:255],
                    "intro": str(row.get("introduction", ""))[:65535] if not pd.isna(row.get("introduction")) else "",
                    "release_date": str(row.get("begin_time", ""))[:255] if not pd.isna(row.get("begin_time")) else "",
                }
    except Exception as e:
        print(f"  data.xlsx: {e}")

    print(f"  CMM movies found: {len(movies)}")

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # 检查哪些已存在
    existing = set()
    cursor.execute("SELECT movie_id FROM movie")
    for row in cursor.fetchall():
        existing.add(row[0])

    new_movies = {k: v for k, v in movies.items() if k not in existing}
    print(f"  New movies to import: {len(new_movies)}")

    batch = []
    for mid, m in new_movies.items():
        batch.append(m)
        if len(batch) >= BATCH:
            cursor.executemany(
                "INSERT IGNORE INTO movie (movie_id, movie_name, intro, release_date) VALUES (%(movie_id)s, %(movie_name)s, %(intro)s, %(release_date)s)",
                batch,
            )
            conn.commit()
            batch.clear()

    if batch:
        cursor.executemany(
            "INSERT IGNORE INTO movie (movie_id, movie_name, intro, release_date) VALUES (%(movie_id)s, %(movie_name)s, %(intro)s, %(release_date)s)",
            batch,
        )
        conn.commit()

    cursor.close()
    conn.close()
    print(f"  Done: imported {len(new_movies)} new movies")


def import_cmm_comments():
    """CMM 短评 (所有 movie_id 现在应该都有了)"""
    print("=== Importing CMM comments ===")
    df = pd.read_excel(f"{CMM_BASE}/comment.xlsx")

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # 验证可用的 movie_id
    cursor.execute("SELECT movie_id FROM movie")
    valid_ids = set(row[0] for row in cursor.fetchall())

    batch = []
    total = 0
    skipped = 0

    for _, row in df.iterrows():
        movie_id = row.get("ID")
        content = str(row.get("comment", "")).strip()
        if pd.isna(movie_id) or not content:
            continue

        movie_id = int(movie_id)
        if movie_id not in valid_ids:
            skipped += 1
            continue

        nickname = str(row.get("name", ""))[:255]
        likes = int(row.get("number_likes", 0)) if not pd.isna(row.get("number_likes")) else 0
        content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

        batch.append({
            "movie_id": movie_id, "nickname": nickname,
            "useful_num": likes, "content": content, "content_hash": content_hash,
            "comment_time": _parse_date(str(row.get("date", ""))),
        })

        if len(batch) >= BATCH:
            _flush(cursor, batch)
            conn.commit()
            total += len(batch)
            batch.clear()

    if batch:
        _flush(cursor, batch)
        conn.commit()
        total += len(batch)

    cursor.close()
    conn.close()
    print(f"  CMM comments: {total} imported, {skipped} skipped (no movie match)")


def import_github_comments():
    """GitHub 短评 — 用电影名匹配"""
    print("=== Importing GitHub comments ===")

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # 预加载电影名映射 (支持多种匹配方式)
    cursor.execute("SELECT movie_id, movie_name FROM movie")
    name_to_id = {}
    for mid, mname in cursor.fetchall():
        mname = mname or ""
        # 中文部分
        cn = re.sub(r"[^一-鿿]", "", mname)
        if cn and len(cn) >= 2:
            name_to_id[cn] = mid
        # 完整名称
        full = mname.strip()
        if full:
            name_to_id[full] = mid

    print(f"  Movie names loaded: {len(name_to_id)}")

    batch = []
    total = 0
    matched = 0
    unmatched = 0

    for root, dirs, files in os.walk(GITHUB_BASE):
        for fname in files:
            if not fname.endswith(".csv") or fname == "note.txt":
                continue

            movie_name_raw = fname.replace(".csv", "")
            cn = re.sub(r"[^一-鿿]", "", movie_name_raw)
            movie_id = name_to_id.get(cn) or name_to_id.get(movie_name_raw)

            fpath = os.path.join(root, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if len(row) < 3:
                            continue
                        content = row[2].strip() if len(row) > 2 else ""
                        if not content:
                            continue
                        nickname = row[1].strip()[:255] if len(row) > 1 else ""
                        likes = _safe_int(row[5]) if len(row) > 5 else 0
                        content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

                        batch.append({
                            "movie_id": movie_id or 0,
                            "nickname": nickname,
                            "useful_num": likes,
                            "content": content[:65535],
                            "content_hash": content_hash,
                            "comment_time": _parse_date(row[0]) if len(row) > 0 else None,
                        })
                        if movie_id:
                            matched += 1
                        else:
                            unmatched += 1

                        if len(batch) >= BATCH:
                            _flush(cursor, batch)
                            conn.commit()
                            total += len(batch)
                            batch.clear()
            except:
                pass

    if batch:
        _flush(cursor, batch)
        conn.commit()
        total += len(batch)

    cursor.close()
    conn.close()
    print(f"  GitHub: {total} total, {matched} matched, {unmatched} unmatched")


def _flush(cursor, batch):
    cursor.executemany(
        """INSERT IGNORE INTO comment (movie_id, nickname, comment_time, useful_num, content, content_hash)
           VALUES (%(movie_id)s, %(nickname)s, %(comment_time)s, %(useful_num)s, %(content)s, %(content_hash)s)""",
        batch,
    )


def _parse_date(s):
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


def _safe_int(v):
    try:
        return int(float(str(v).strip()))
    except:
        return 0


if __name__ == "__main__":
    import_cmm_movies()
    import_cmm_comments()
    import_github_comments()

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), COUNT(DISTINCT movie_id) FROM comment")
    total, movies = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM movie")
    movie_count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    print(f"\n=== Final ===")
    print(f"  movies: {movie_count}")
    print(f"  comments: {total:,}")
    print(f"  movies with comments: {movies}")
