import os
from typing import List, Union


def cleanup_temp_file(file_paths: Union[str, List[str]]):
    """异步批量删除临时文件

    Args:
        file_paths: 单个文件路径字符串或文件路径列表
    """
    if isinstance(file_paths, str):
        file_paths = [file_paths]

    for file_path in file_paths:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"成功删除: {file_path}")
            else:
                print(f"文件不存在: {file_path}")
        except Exception as e:
            print(f"删除失败 [{file_path}]: {str(e)}")