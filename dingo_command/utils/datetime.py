from urllib.parse import unquote

from dateutil import parser
import subprocess
import re
from datetime import datetime, timedelta
import pytz
from typing import Tuple, Optional

TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
# 东八区时间格式化
TIMESTAMP_FORMAT_D8Q = '%Y-%m-%d-%H-%M-%S'
# 东八区时间格式化转化为不带连字符-
TIMESTAMP_FORMAT_D8Q_STR = '%Y%m%d%H%M%S'
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

def format_d8q_timestamp_without_hyphens():
    # 获取当前 UTC 时间
    utc_now = get_now_time()
    # 将 UTC 时间转换为东八区时间 (Asia/Shanghai)
    cst_timezone = pytz.timezone('Asia/Shanghai')
    cst_now = utc_now.astimezone(cst_timezone)
    # 格式化
    return cst_now.strftime(TIMESTAMP_FORMAT_D8Q_STR)

def switch_time_to_time(begin, end):
    return unquote(begin).replace(" ", "-").replace(":", "-") + "_to_" + unquote(end).replace(" ", "-").replace(":", "-")

def convert_timestamp_to_date(begin, end):
    dt_start = datetime.strptime(begin, "%Y-%m-%d %H:%M:%S")
    dt_end = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")

    # 提取日期部分（自动去掉时间）
    formatted_date_start = dt_start.date().isoformat()
    formatted_date_end = dt_end.date().isoformat()
    return formatted_date_start + "_to_" + formatted_date_end


def get_system_timezone() -> Tuple[Optional[str], Optional[str]]:
    """获取系统时区缩写和偏移量

    Returns:
        tuple: (时区缩写, 时区偏移量) 例如 ('CST', '+0800')
    """
    try:
        # 执行 date 命令获取时区信息
        result = subprocess.run(['date', '+%Z %z'],
                                capture_output=True,
                                text=True,
                                check=True)
        output = result.stdout.strip()

        # 解析输出 (例如 "CST +0800")
        match = re.match(r'([A-Z]{3})\s*([+-]\d{4})', output)
        if match:
            return match.group(1), match.group(2)
        return None, None

    except subprocess.CalledProcessError as e:
        print(f"获取时区失败: {e}")
        return "UTC", None


def get_system_time_range(time_range: str):
    """根据参数获取指定时间范围的UTC时间

    Args:
        time_range: 时间范围，可选值:
            'current_month' - 当月
            'one_hour_ago' - 最近一小时
            'one_day_ago' - 最近一天
            'one_week_ago' - 最近七天
            'month30_ago' - 最近30天

    Returns:
        dict: 包含'start'和'end'键的字典，值为对应的UTC时间
    """
    # 获取时区信息
    tz_abbr, tz_offset = get_system_timezone()

    if not tz_abbr or not tz_offset:
        print("无法确定系统时区，使用UTC时间")
        tz = pytz.UTC
    else:
        # 创建固定偏移时区
        offset_hours = int(tz_offset[:3])
        offset_minutes = int(tz_offset[0] + tz_offset[3:])
        tz = pytz.FixedOffset(offset_hours * 60 + offset_minutes)

    # 获取当前本地时间并标记时区
    # now = datetime.now(tz)
    now = datetime.now()

    # 根据参数计算不同时间范围
    if time_range == 'current_month':
        # 当月范围
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = (now.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif time_range == 'one_hour_ago':
        # 最近一小时
        start = now - timedelta(hours=1)
        end = now
    elif time_range == 'one_day_ago':
        # 最近一天
        start = now - timedelta(days=1)
        end = now
    elif time_range == 'one_week_ago':
        # 最近七天
        start = now - timedelta(days=7)
        end = now
    elif time_range == 'month30_ago':
        # 最近30天
        start = now - timedelta(days=30)
        end = now
    else:
        print(f"不支持或自定义时间范围参数[{time_range}], 不进行处理")
        return None, None

    return start.strftime('%Y-%m-%d %H:%M:%S %Z'), end.strftime('%Y-%m-%d %H:%M:%S %Z')


    # 转换为UTC时间
    return start.astimezone(pytz.UTC), end.astimezone(pytz.UTC)

def get_system_current_time():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')

def system_time_to_utc(system_time_str: str, time_format: str = '%Y-%m-%d %H:%M:%S'):
    try:
        if system_time_str is None:
            return system_time_str

        # 获取时区信息
        tz_abbr, tz_offset = get_system_timezone()

        if not tz_abbr or not tz_offset:
            print("Warning: Could not determine system timezone, using UTC")
            tz = pytz.UTC
        else:
            # Create timezone from offset
            offset_hours = int(tz_offset[:3])
            offset_minutes = int(tz_offset[0] + tz_offset[3:])
            tz = pytz.FixedOffset(offset_hours * 60 + offset_minutes)

        # Parse input time string (naive datetime)
        local_time = datetime.strptime(system_time_str, time_format)

        # Localize and convert to UTC
        localized_time = tz.localize(local_time)
        return localized_time.astimezone(pytz.UTC)
    except Exception as e:
        print(f"Unexpected error during time conversion: {e}")
        return system_time_str


def utc_to_system_time(utc_time_str: str, time_format: str = '%Y-%m-%dT%H:%M:%S'):
    try:
        if utc_time_str is None:
            return None

        # 1. 首先将UTC时间字符串解析为时区感知的datetime对象
        utc_time = datetime.strptime(utc_time_str, time_format).replace(tzinfo=pytz.UTC)

        # 2. 获取系统时区信息
        tz_abbr, tz_offset = get_system_timezone()

        if not tz_abbr or not tz_offset:
            print("Warning: Could not determine system timezone, using Asia/Shanghai (UTC+8) as default")
            local_tz = pytz.timezone('Asia/Shanghai')  # 默认使用中国时区
        else:
            # 3. 正确处理时区偏移量（例如"+0800"）
            # 提取符号和数值
            sign = -1 if tz_offset[0] == '-' else 1
            hours = int(tz_offset[1:3])
            minutes = int(tz_offset[3:5])


            # 4. 创建正确的时区对象
            if tz_abbr in pytz.all_timezones:
                local_tz = pytz.timezone(tz_abbr)
            else:
                # 使用偏移量创建固定时区
                total_minutes = sign * (hours * 60 + minutes)
                local_tz = pytz.FixedOffset(total_minutes)

        # 5. 转换为本地时间
        local_time = utc_time.astimezone(local_tz)

        return local_time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"Unexpected error during time conversion: {e}")
        return None

if __name__ == "__main__":
    # 测试不同时间范围
    ranges_to_test = ['current_month', 'one_hour_ago', 'one_day_ago', 'one_week_ago', 'month30_ago']

    for time_range in ranges_to_test:
        try:
            print(f"\n=== {time_range} ===")
            begin, end = get_system_time_range(time_range)
            print(f"\n=== 开始时间：{begin}， 结束时间：{end} ===")
        except ValueError as e:
            print(e)

    system_time = "2025-06-25 17:58:00"
    system_to_utc_time = system_time_to_utc(system_time)
    print(f"\n=====系统时间转化为UTC时间:{system_to_utc_time}")

    utc_time = "2025-06-25 09:58:00"
    utc_to_system_time_str = utc_to_system_time(utc_time)
    print(f"\n=====UTC时间转化为系统时间:{utc_to_system_time_str}")