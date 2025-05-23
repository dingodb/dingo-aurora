import json
import os
import shutil
from oslo_log import log
import pandas as pd
from openpyxl.reader.excel import load_workbook
from openpyxl.styles import Border, Side

from dingo_command.utils.constant import RATING_SUMMARY_TEMPLATE_FILE_DIR
from dingo_command.common.cloudkitty_client import CloudKittyClient

LOG = log.getLogger(__name__)

# 定义边框样式
thin_border = Border(
    left=Side(border_style="thin", color="000000"),  # 左边框
    right=Side(border_style="thin", color="000000"),  # 右边框
    top=Side(border_style="thin", color="000000"),  # 上边框
    bottom=Side(border_style="thin", color="000000")  # 下边框
)

class CloudKittyService:

    def download_rating_summary_excel(self, result_file_path):
        # 模板路径
        current_template_file = os.getcwd() + RATING_SUMMARY_TEMPLATE_FILE_DIR
        # 对应类型的模板不存在
        if current_template_file is None:
            return None
        try:
            print(f"current_template_file:{current_template_file}, result_file_path:{result_file_path}")
            # 复制模板文件到临时目录
            shutil.copy2(current_template_file, result_file_path)
            # 计费汇总的文件
            self.query_data_and_create_rating_summary_excel(result_file_path)

        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def query_data_and_create_rating_summary_excel(self, result_file_path):
        try:
            # 导出的excel数据
            excel_rating_summary_data = []
            # 读取数据数据
            storage_dataFrames = CloudKittyClient().get_storage_dataframes()
            # 类型是空
            if storage_dataFrames is not None:
                # 写入数据
                for temp in storage_dataFrames:
                    begin = temp["begin"] if temp is not None and "begin" in temp else None
                    end = temp["end"] if temp is not None and "end" in temp else None
                    project_id = temp["tenant_id"] if temp is not None and "tenant_id" in temp else None
                    resources_json = json.dumps(temp["resources"]) if temp is not None and "resources" in temp else None

                    # 修改或添加新数据
                    temp_rating_summary_data = {'Begin': begin,
                                       'End': end,
                                       'Project ID': project_id,
                                       'Resources': resources_json,}
                    # 加入excel导出数据列表
                    excel_rating_summary_data.append(temp_rating_summary_data)
            # 加载模板文件
            book = load_workbook(result_file_path)
            sheet = book['ratingSummary']  # 默认使用第一个工作表
            # 确定起始写入行号
            start_row = 2  # 自动追加到最后一行之后
            # 写入数据到模板文件
            for idx, row in pd.DataFrame(excel_rating_summary_data).iterrows():
                for col_idx, value in enumerate(row, start=1):  # 列从 1 开始
                    sheet.cell(row=start_row + idx, column=col_idx, value=value)
            # 保存修改
            book.save(result_file_path)
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e