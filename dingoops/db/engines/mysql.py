# mysql连接
import threading
from oslo_config import cfg
from oslo_db.sqlalchemy import session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

CONF = cfg.CONF

# 数据库连接地址
DATABASE_URL = CONF.database.connection
# print(DATABASE_URL)

# 创建连接池
# engine = create_engine(
#     DATABASE_URL,
#     pool_size=10,  # 连接池的大小
#     max_overflow=50,  # 超过连接池大小时，允许的最大连接数
#     pool_timeout=30,  # 获取连接时的超时时间（秒）
#     pool_recycle=60  # 连接的生命周期（秒）
# )

_LOCK = threading.Lock()
_FACADE = None

def _create_facade_lazily():
    global _LOCK
    with _LOCK:
        global _FACADE
        if _FACADE is None:
            _FACADE = session.EngineFacade(
                CONF.database.connection,
                **dict(CONF.database)
            )
        return _FACADE

def get_engine():
    facade = _create_facade_lazily()
    return facade.get_engine()


def get_session(**kwargs):
    facade = _create_facade_lazily()
    return facade.get_session(**kwargs)

# # 从数据库连接池中读取连接
# def get_session():
#     Session = sessionmaker(bind=engine)
#     session = Session()
#     return session