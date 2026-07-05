# 豆瓣电影信息采集与分析系统

面向豆瓣电影的网络爬虫系统，实现电影基本信息、评分、短评与影评的自动采集、存储与分析。

## 项目概述

- **开发语言**: Python 3.11
- **爬虫框架**: Scrapy 2.11
- **数据库**: MySQL 8.0 + Redis 7
- **数据分析**: Pandas + NumPy + pyecharts
- **Web 展示**: Flask + Bootstrap 5

## 系统架构

```
种子 URL (Top250)
     │
     ▼
电影列表爬虫 ──→ 电影详情爬虫
                     │
          ┌──────────┼──────────┐
          ▼                     ▼
     短评采集模块           影评采集模块
          │                     │
          └──────────┬──────────┘
                     ▼
              MySQL 数据库
                     │
          ┌──────────┼──────────┐
          ▼                     ▼
     数据分析模块           Web 展示系统
```

**链式扩展策略**: 从 Top250 出发，通过每部电影详情页的"喜欢这部电影的人也喜欢"推荐列表发现新电影，经两轮扩展覆盖万级电影。

## 数据库设计

6 张核心表，满足第三范式：

| 表名 | 用途 | 数据量 |
|---|---|---|
| `movie` | 电影基本信息 + 评分 | 67,602 |
| `movie_person` | 导演/编剧/演员关系 (N:1 → movie) | 355,956 |
| `movie_genre` | 类型标签 (N:1 → movie) | 123,673 |
| `comment` | 短评 | 640,667 |
| `review` | 影评 | 25,897 |
| `crawl_log` | 爬虫日志 | — |

## 快速开始

### 环境准备

```bash
# 创建虚拟环境
python3 -m venv venv && source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 安装 Twisted 兼容版本（Scrapy 2.11 需要 Twisted < 25）
pip install "Twisted>=23,<25"
```

### 启动数据库

```bash
# MySQL (已初始化: 数据库 douban_movie, 用户 crawler/123456)
sudo service mysql start

# Redis
redis-server
```

### 导入公开数据集（快速获得数据）

```bash
# 导入电影元数据 (67K 部)
python import_kaggle.py

# 导入短评 (64 万条)
python import_comments_v2.py
```

### 运行爬虫

```bash
cd douban_movie_system

# 测试模式：爬 5 部电影
redis-cli DEL "douban_crawler:dupefilter:fingerprints"
scrapy crawl movie -a test=1

# 爬 100 部电影（验证链式扩展）
scrapy crawl movie -a max_movies=100

# 爬短评（前 10 部热门电影，每部 5 页）
scrapy crawl comment -a max_movies=10 -a max_pages=5

# 爬影评（前 100 部热门电影）
scrapy crawl review -a max_movies=100

# 后台运行（大规模采集）
nohup scrapy crawl review -a max_movies=500 > crawl.log 2>&1 &
```

### 数据分析

```bash
# 生成统计图表 (HTML)
python analysis/charts.py

# 启动 Web 展示
python web/app.py
# → http://localhost:5000
```

## 项目结构

```
douban_crawler/
├── douban_movie_system/
│   ├── scrapy.cfg                    # Scrapy 项目配置
│   ├── crawler/                      # 爬虫核心
│   │   ├── spiders/
│   │   │   ├── movie_spider.py       # 电影爬虫 (Top250 + 推荐链)
│   │   │   ├── comment_spider.py     # 短评爬虫
│   │   │   └── review_spider.py      # 影评爬虫
│   │   ├── items.py                  # 数据模型 (MovieItem / CommentItem / ReviewItem)
│   │   ├── pipelines.py              # MySQL 批量写入管道
│   │   ├── middlewares.py            # 反爬中间件 (UA轮换 / Cookie注入 / 反ban重试)
│   │   ├── dupefilter.py             # Redis 持久化去重
│   │   └── settings.py               # 爬虫配置
│   ├── database/
│   │   └── mysql.sql                 # 建表 DDL
│   ├── analysis/
│   │   ├── movie_analysis.py         # 数据分析 (Pandas + SQLAlchemy)
│   │   └── charts.py                 # 图表生成 (pyecharts)
│   └── web/
│       ├── app.py                    # Flask 应用
│       └── templates/                # Jinja2 模板
├── import_kaggle.py                  # Kaggle 数据集导入脚本
├── import_comments_v2.py             # 短评数据集整合导入
├── requirements.txt
├── dbdesign                          # 数据库设计文档
├── masterplan                        # 项目设计说明书
└── README.md
```

## 反爬策略

豆瓣对爬虫有较强的反爬机制。本项目采用多层对抗：

| 策略 | 实现 |
|---|---|
| User-Agent 轮换 | `RandomUserAgentMiddleware` — 6 个 UA 随机切换 |
| Cookie 注入 | `CookieInjectMiddleware` — 预置登录态绕过 JS 挑战 |
| 自适应限速 | AutoThrottle — 根据响应延迟自动调整请求间隔 |
| 请求去重 | `RedisDupeFilter` — 跨重启持久化已抓 URL |
| 失败重试 | Scrapy RetryMiddleware — 403/418/5xx 自动重试 3 次 |
| 重定向拦截 | `SecDoubanRedirectMiddleware` — 阻止跟踪到反爬安全页面 |
| 链式发现 | 推荐列表链式扩展，分散请求压力 |

> **注意**: 豆瓣反爬会限制单 IP 的请求频率。大规模采集建议使用多账号 Cookie + 代理 IP 轮换，或直接使用公开数据集补充。

## 数据来源

| 数据 | 来源 | 方法 |
|---|---|---|
| 电影元数据 (67K) | Kaggle douban-movies 数据集 | `import_kaggle.py` |
| 短评 (640K) | CMM + GitHub + HuggingFace | `import_comments_v2.py` |
| 影评 (25K) | 爬虫采集 + 长内容短评转换 | Scrapy spider |

## 数据分析维度

- 评分分布统计
- 电影类型分布
- 国家/地区分布
- 导演排行榜（平均评分）
- 高分电影 Top 20
- 上映年份趋势
- 短评数量统计

## License

本项目仅用于课程学习与研究用途。豆瓣电影数据版权归豆瓣所有。
