import pymysql

conn = pymysql.connect(
    host='127.0.0.1',
    port=3306,
    user='crawler',
    password='123456',
    database='douban_movie',
    charset='utf8mb4'
)

print("连接成功")
conn.close()