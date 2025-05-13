# mysql的工具类
import pymysql
from dbutils.pooled_db import PooledDB

class MySqlUtils:

    # def __init__(self, host, port, user, password, database):
    #     self.host = host
    #     self.port = port
    #     self.user = user
    #     self.password = password
    #     self.database = database

    def __init__(self, host, port, user, password, database):
        # 使用池化连接
        self.pool = PooledDB(
            creator=pymysql,
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            autocommit=False,
            maxconnections=300,  # 连接池允许的最大连接数
            blocking=True,  # 连接池满时阻塞等待
            ping=5  # 每7次查询检查一次连接活性
        )

    def connect(self):
        try:
            return self.pool.connection()
        except Exception as e:
            print(f"Error connecting to MySQL: {e}")
            raise e

    def insert_many(self, sql, data):
        try:
            # 连接数据库
            with self.connect() as connection:
                with connection.cursor() as cursor:
                    cursor.executemany(sql, data)
                    connection.commit()  # 显式提交事务
                print("Data inserted successfully.")
        except Exception as e:
            print(f"Error inserting data: {e}")
            connection.rollback()
            raise e

    def insert_one(self, sql, data):
        try:
            # 连接数据库
            with self.connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(sql, data)
                    connection.commit()  # 显式提交事务
                print("Data inserted successfully.")
        except Exception as e:
            print(f"Error inserting data: {e}")
            connection.rollback()
            raise e