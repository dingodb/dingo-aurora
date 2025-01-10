# 常用处理方法

def format_excel_str(origin:str):
    # 判空
    if not origin:
        return origin
    # 去除两端的两端的空白字符
    new_value = origin.strip()
    # 返回
    return new_value