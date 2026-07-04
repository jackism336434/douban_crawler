import scrapy


class MovieItem(scrapy.Item):
    """电影基本信息 + 评分"""
    movie_id = scrapy.Field()        # 豆瓣电影ID (BIGINT)
    movie_name = scrapy.Field()      # 电影名称
    poster_url = scrapy.Field()      # 海报图片链接
    intro = scrapy.Field()           # 剧情简介
    country = scrapy.Field()         # 制片国家/地区
    language = scrapy.Field()        # 语言
    release_date = scrapy.Field()    # 上映日期
    duration = scrapy.Field()        # 片长
    imdb_url = scrapy.Field()        # IMDb链接
    alias_name = scrapy.Field()      # 又名

    douban_score = scrapy.Field()    # 豆瓣评分
    rating_count = scrapy.Field()    # 评价人数
    comment_count = scrapy.Field()   # 短评总数
    review_count = scrapy.Field()    # 影评总数

    # 关联数据 (pipeline 中拆入子表)
    directors = scrapy.Field()       # list[str]
    writers = scrapy.Field()         # list[str]
    actors = scrapy.Field()          # list[str]
    genres = scrapy.Field()          # list[str]


class CommentItem(scrapy.Item):
    """短评"""
    movie_id = scrapy.Field()        # 豆瓣电影ID
    nickname = scrapy.Field()        # 评论者昵称
    comment_time = scrapy.Field()    # 评论时间
    useful_num = scrapy.Field()      # 有用人数
    content = scrapy.Field()         # 评论内容


class ReviewItem(scrapy.Item):
    """影评"""
    movie_id = scrapy.Field()        # 豆瓣电影ID
    nickname = scrapy.Field()        # 影评者昵称
    review_time = scrapy.Field()     # 影评时间
    useful_num = scrapy.Field()      # 有用人数
    useless_num = scrapy.Field()     # 无用人数
    share_num = scrapy.Field()       # 转发人数
    reply_num = scrapy.Field()       # 回应人数
    content = scrapy.Field()         # 影评内容
