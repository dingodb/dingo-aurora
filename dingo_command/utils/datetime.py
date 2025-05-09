from dateutil import parser
from datetime import datetime
from datetime import timedelta
import pytz

TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
# 东八区时间格式化
TIMESTAMP_FORMAT_D8Q = '%Y-%m-%d-%H-%M-%S'
# excel中时间格式
EXCEL_TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S'


def change_to_utc_time_and_format(timestamp_str, new_format=TIMESTAMP_FORMAT):
    timestamp = parser.parse(timestamp_str)
    timestamp = timestamp - timedelta(seconds=(datetime.now() - datetime.utcnow()).total_seconds())
    return timestamp.strftime(new_format)


def format_unix_timestamp(timestamp, date_format=TIMESTAMP_FORMAT):
    return datetime.fromtimestamp(float(timestamp)).strftime(date_format)


def get_now_time():
    return datetime.now()

def get_now_time_in_timestamp_format(new_format=TIMESTAMP_FORMAT):
    return get_now_time().strftime(new_format)

def get_time_delta(now, old):
    delta = now - old
    return int(delta.total_seconds())


def change_timestamp_to_datetime(timestamp):
    return datetime.fromtimestamp(timestamp)

def change_excel_date_to_timestamp(datetime_str, date_format=EXCEL_TIMESTAMP_FORMAT):
    # 使用 strptime 将时间字符串转为 datetime 对象
    dt_object = datetime.strptime(datetime_str, date_format)
    # 使用 timestamp 将 datetime 对象转为时间戳
    timestamp = dt_object.timestamp()
    return timestamp

# -----------------------------
def get_delta_old(old):
    now = get_now_time()
    return get_time_delta(now, old)


def format_d8q_timestamp():
    # 获取当前 UTC 时间
    utc_now = get_now_time()
    # 将 UTC 时间转换为东八区时间 (Asia/Shanghai)
    cst_timezone = pytz.timezone('Asia/Shanghai')
    cst_now = utc_now.astimezone(cst_timezone)
    # 格式化
    return cst_now.strftime(TIMESTAMP_FORMAT_D8Q)