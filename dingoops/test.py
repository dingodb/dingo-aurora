from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from db.models.asset.models import Asset

#链接数据库，可以使用配置文件进行定义
engine = create_engine("mysql+pymysql://root:mxBkxh0XVtM9kVm7Q71mCbw6P2hGxrU5eBJWx1Oy@10.220.58.250:3306/dingoops?charset=utf8mb3", echo=True)
with engine.connect() as conn:
    result = conn.execute('SELECT 1')
    print(result.fetchone())