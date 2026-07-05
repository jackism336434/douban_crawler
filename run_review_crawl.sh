#!/bin/bash
# 后台影评爬虫 — 多次运行，逐步累积
# 用法: bash run_review_crawl.sh

cd /home/jack/douban_crawler/douban_movie_system

for round in 1 2 3 4 5; do
    echo "=== Round $round ==="
    redis-cli DEL "douban_crawler:dupefilter:fingerprints" 2>/dev/null

    scrapy crawl review -a max_movies=500 -a max_pages=2

    count=$(mysql -u crawler -p123456 -h 127.0.0.1 douban_movie -sN \
        -e "SELECT COUNT(*) FROM review")
    echo "Total reviews: $count"

    # 等 5 分钟再下一轮 (给 IP 冷却)
    echo "Cooling down 5 minutes..."
    sleep 300
done
