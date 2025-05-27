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

    def list_messages(self, table_name, query_params, page, page_size, sort_keys, sort_dirs):
        try:
            with self.connect() as connection:
                with connection.cursor() as cursor:
                    # 构建查询条件
                    conditions = []
                    for key, value in query_params.items():
                        conditions.append(f"{key} = %s")
                    where_clause = " AND ".join(conditions) if conditions else "1=1"
                    # 构建排序条件
                    sort_clause = ""
                    if sort_keys and sort_dirs:
                        sort_clause = f"ORDER BY {sort_keys} {sort_dirs}"
                    # 构建分页条件
                    offset = (page - 1) * page_size
                    limit_clause = f"LIMIT {offset}, {page_size}"
                    # sql语句
                    sql = f"SELECT * FROM {table_name} WHERE {where_clause} {sort_clause} {limit_clause}"
                    print(f"Executing SQL: {sql} ")
                    cursor.execute(sql, list(query_params.values()))
                    columns = [col[0] for col in cursor.description]
                    data = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return data
        except Exception as e:
            print(f"Error listing messages: {e}")
            raise e