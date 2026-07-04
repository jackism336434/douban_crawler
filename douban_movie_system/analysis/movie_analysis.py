"""
豆瓣电影数据分析模块。

使用 SQLAlchemy 读取 MySQL 数据，Pandas 进行统计分析，
pyecharts 生成可视化图表 (HTML 文件)。

运行方式:
    cd douban_movie_system
    python analysis/movie_analysis.py
"""

import os
import sys

import pandas as pd
from sqlalchemy import create_engine

# 输出目录
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 数据库连接
ENGINE = create_engine(
    "mysql+pymysql://crawler:123456@127.0.0.1:3306/douban_movie?charset=utf8mb4"
)


def query(sql: str) -> pd.DataFrame:
    """执行 SQL 查询，返回 DataFrame"""
    return pd.read_sql(sql, ENGINE)


# ============================================================
# 分析函数
# ============================================================


def score_distribution():
    """评分分布: 各评分段电影数量"""
    sql = """
        SELECT
            CASE
                WHEN douban_score >= 9.0 THEN '9.0-10'
                WHEN douban_score >= 8.0 THEN '8.0-8.9'
                WHEN douban_score >= 7.0 THEN '7.0-7.9'
                WHEN douban_score >= 6.0 THEN '6.0-6.9'
                WHEN douban_score >= 5.0 THEN '5.0-5.9'
                ELSE '0-4.9'
            END AS score_range,
            COUNT(*) AS cnt
        FROM movie
        WHERE douban_score IS NOT NULL
        GROUP BY score_range
        ORDER BY MIN(douban_score) DESC
    """
    return query(sql)


def genre_distribution():
    """类型分布: 各类型电影数量"""
    sql = """
        SELECT genre_name, COUNT(*) AS cnt
        FROM movie_genre
        GROUP BY genre_name
        ORDER BY cnt DESC
    """
    return query(sql)


def country_distribution():
    """国家/地区分布"""
    sql = """
        SELECT
            TRIM(SUBSTRING_INDEX(country, '/', 1)) AS primary_country,
            COUNT(*) AS cnt
        FROM movie
        WHERE country IS NOT NULL AND country != ''
        GROUP BY primary_country
        ORDER BY cnt DESC
        LIMIT 20
    """
    return query(sql)


def top_directors(min_movies: int = 3):
    """导演排行榜 (至少 min_movies 部电影)"""
    sql = f"""
        SELECT person_name, COUNT(*) AS cnt,
               ROUND(AVG(m.douban_score), 1) AS avg_score
        FROM movie_person mp
        JOIN movie m ON mp.movie_id = m.movie_id
        WHERE mp.role = 'director'
          AND m.douban_score IS NOT NULL
        GROUP BY person_name
        HAVING cnt >= {min_movies}
        ORDER BY avg_score DESC
        LIMIT 30
    """
    return query(sql)


def top_actors(min_movies: int = 5):
    """演员排行榜 (至少 min_movies 部电影)"""
    sql = f"""
        SELECT person_name, COUNT(*) AS cnt,
               ROUND(AVG(m.douban_score), 1) AS avg_score
        FROM movie_person mp
        JOIN movie m ON mp.movie_id = m.movie_id
        WHERE mp.role = 'actor'
          AND m.douban_score IS NOT NULL
        GROUP BY person_name
        HAVING cnt >= {min_movies}
        ORDER BY cnt DESC
        LIMIT 30
    """
    return query(sql)


def top_movies(limit: int = 20):
    """高分电影排行榜"""
    sql = f"""
        SELECT movie_name, douban_score, rating_count
        FROM movie
        WHERE douban_score IS NOT NULL
          AND rating_count > 1000
        ORDER BY douban_score DESC, rating_count DESC
        LIMIT {limit}
    """
    return query(sql)


def release_year_distribution():
    """上映年份分布"""
    sql = """
        SELECT
            CASE
                WHEN release_date REGEXP '[0-9]{{4}}'
                THEN SUBSTRING(release_date, 1, 4)
                ELSE '未知'
            END AS year,
            COUNT(*) AS cnt
        FROM movie
        WHERE release_date IS NOT NULL AND release_date != ''
        GROUP BY year
        ORDER BY year
    """
    return query(sql)


def comment_volume_stats():
    """短评数量统计"""
    sql = """
        SELECT
            m.movie_name,
            m.comment_count,
            COUNT(c.comment_id) AS actual_comment_count
        FROM movie m
        LEFT JOIN comment c ON m.movie_id = c.movie_id
        GROUP BY m.movie_id
        ORDER BY m.comment_count DESC
        LIMIT 20
    """
    return query(sql)


# ============================================================
# 统计汇总
# ============================================================


def system_stats():
    """系统总览统计"""
    stats = {}
    stats["total_movies"] = query(
        "SELECT COUNT(*) FROM movie"
    ).iloc[0, 0]
    stats["total_comments"] = query(
        "SELECT COUNT(*) FROM comment"
    ).iloc[0, 0]
    stats["total_reviews"] = query(
        "SELECT COUNT(*) FROM review"
    ).iloc[0, 0]
    stats["avg_score"] = query(
        "SELECT ROUND(AVG(douban_score), 2) FROM movie WHERE douban_score IS NOT NULL"
    ).iloc[0, 0]
    stats["total_genres"] = query(
        "SELECT COUNT(DISTINCT genre_name) FROM movie_genre"
    ).iloc[0, 0]
    stats["total_persons"] = query(
        "SELECT COUNT(DISTINCT person_name) FROM movie_person"
    ).iloc[0, 0]

    print("=" * 50)
    print("豆瓣电影数据统计")
    print("=" * 50)
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print("=" * 50)
    return stats


if __name__ == "__main__":
    system_stats()
    print("\n分析完成!")
