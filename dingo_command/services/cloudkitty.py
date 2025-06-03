import json
import os
import platform
import shutil
from datetime import datetime

import pandas as pd
from openpyxl.reader.excel import load_workbook
from openpyxl.styles import Border, Side
from oslo_log import log
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Table

from dingo_command.common.cloudkitty_client import CloudKittyClient
from dingo_command.utils.constant import RATING_SUMMARY_TEMPLATE_FILE_DIR, RATING_SUMMARY_DETAIL_EN_TEMPLATE_FILE_DIR, \
    RATING_SUMMARY_DETAIL_ZH_TEMPLATE_FILE_DIR

LOG = log.getLogger(__name__)

# 定义边框样式
thin_border = Border(
    left=Side(border_style="thin", color="000000"),  # 左边框
    right=Side(border_style="thin", color="000000"),  # 右边框
    top=Side(border_style="thin", color="000000"),  # 上边框
    bottom=Side(border_style="thin", color="000000")  # 下边框
)

class CloudKittyService:

    def download_rating_summary_excel(self, result_file_path, query_params):
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
            self.query_data_and_create_rating_summary_excel(result_file_path, query_params)

        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def query_data_and_create_rating_summary_excel(self, result_file_path, query_params):
        try:
            # 导出的excel数据
            excel_rating_summary_data = []
            # 读取数据数据
            storage_dataFrames = CloudKittyClient().get_storage_dataframes(query_params)
            # 类型是空
            if storage_dataFrames is not None:
                # 写入数据
                for temp in storage_dataFrames:
                    begin_str = None
                    if temp is not None and "begin" in temp:
                        # 转换为datetime对象
                        dt = datetime.strptime(temp["begin"], "%Y-%m-%dT%H:%M:%S")
                        # 格式化为不带T的字符串
                        begin_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                    end_str = None
                    if temp is not None and "end" in temp:
                        # 转换为datetime对象
                        dt = datetime.strptime(temp["end"], "%Y-%m-%dT%H:%M:%S")
                        # 格式化为不带T的字符串
                        end_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                    project_id = temp["tenant_id"] if temp is not None and "tenant_id" in temp else None
                    resources_json = json.dumps(temp["resources"]) if temp is not None and "resources" in temp else None

                    # 修改或添加新数据
                    temp_rating_summary_data = {'Begin': begin_str,
                                       'End': end_str,
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
                    sheet.cell(row=start_row + idx, column=col_idx, value=value).border = thin_border
            # 保存修改
            book.save(result_file_path)
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e


    def download_rating_summary_detail_pdf(self, result_file_pdf_path, detail, language):
        try:
            # 生成计费汇总租户详情数据
            temp_data = self.generate_rating_summary_detail_data(detail, language)
            # 生成PDF文件
            self.create_rating_summary_detail_pdf_with_table(temp_data, result_file_pdf_path)

        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def download_rating_summary_detail_execl(self, result_file_execl_path, detail, language):
        if language is None or language == "EN":
            # 模板路径
            current_template_file = os.getcwd() + RATING_SUMMARY_DETAIL_EN_TEMPLATE_FILE_DIR
        else:
             # 模板路径
             current_template_file = os.getcwd() + RATING_SUMMARY_DETAIL_ZH_TEMPLATE_FILE_DIR

        # 对应类型的模板不存在
        if current_template_file is None:
            return None

        try:
            print(f"current_template_file:{current_template_file}, result_file_execl_path:{result_file_execl_path}")
            # 复制模板文件到临时目录
            shutil.copy2(current_template_file, result_file_execl_path)

            # 生成计费汇总租户详情数据
            temp_data = self.generate_rating_summary_detail_data(detail, language)

            # 加载模板文件
            book = load_workbook(result_file_execl_path)
            detail_sheet = book['ratingSummaryDetail']

            # 插入项目ID、开始时间、结束时间数据
            start_row = 1
            for idx, item in enumerate(temp_data):
                # 获取字典的键值对
                value = list(item.values())[0]
                # 写入第二列
                detail_sheet.cell(row=start_row + idx, column=2, value=value).border = thin_border

            # 插入资源类型费率
            start_row = 5  # 从第5行开始插入
            for idx, item in enumerate(temp_data[4:]):
                # 获取字典的键值对
                key = list(item.keys())[0]
                value = list(item.values())[0]

                # 写入第一列和第二列
                detail_sheet.cell(row=start_row + idx, column=1, value=key).border = thin_border
                detail_sheet.cell(row=start_row + idx, column=2, value=value).border = thin_border

            # 保存修改
            book.save(result_file_execl_path)
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def generate_rating_summary_detail_data(self, ratingSummaryDetailList, language):
        try:
            if ratingSummaryDetailList is None:
                return None
            temp_data = []
            # 项目ID
            tenant_id = None if ratingSummaryDetailList is None else ratingSummaryDetailList[0].tenant_id
            tenant_name = None if ratingSummaryDetailList is None else ratingSummaryDetailList[0].tenant_name
            if language is None or language == "EN":
                if tenant_name is None:
                    temp_data.append({'Tenant ID': tenant_id})
                else:
                    temp_data.append({'Tenant Name': tenant_name})
            else:
                if tenant_name is None:
                    temp_data.append({'项目ID':tenant_id})
                else:
                    temp_data.append({'项目名称':tenant_name})
            # 开始时间
            begin_datatime = None if ratingSummaryDetailList is None or ratingSummaryDetailList[0].flavor is None \
                             or ratingSummaryDetailList[0].flavor is None or ratingSummaryDetailList[0].flavor[0] is None \
                            else ratingSummaryDetailList[0].flavor[0].begin
            begin_datatime_str = None
            if begin_datatime is not None:
                # 转换为datetime对象
                dt = datetime.strptime(begin_datatime, "%Y-%m-%dT%H:%M:%S")
                # 格式化为不带T的字符串
                begin_datatime_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            if language is None or language == "EN":
                temp_data.append({'Begin Time': begin_datatime_str})
            else:
                temp_data.append({'开始时间': begin_datatime_str})

            # 结束时间
            end_date = None if ratingSummaryDetailList is None else ratingSummaryDetailList[0].end
            if language is None or language == "EN":
                temp_data.append({'End Time': end_date})
                # Res type、费率
                temp_data.append({'Res Type': 'Rate'})
            else:
                temp_data.append({'结束时间': end_date})
                # Res type、费率
                temp_data.append({'资源类型': '费率'})

            temp_instance_flavor_data = []
            temp_non_instance_data = []
            temp_total_rating_data = []
            for ratingSummaryDetail in ratingSummaryDetailList:
                if ratingSummaryDetail.service == "总计" or ratingSummaryDetail.service == "Total":
                    if language is None or language == "EN":
                        temp_total_rating_data.append({'Total':ratingSummaryDetail.total})
                    else:
                        temp_total_rating_data.append({'总计':ratingSummaryDetail.total})
                elif ratingSummaryDetail.service == "instance":
                    temp_instance_flavor_data.append({'instance':ratingSummaryDetail.total})
                    if ratingSummaryDetail.flavor is not None:
                        if language is None or language == "EN":
                            temp_instance_flavor_data.append({'  VM Type': 'Rate'})
                        else:
                            temp_instance_flavor_data.append({'  云主机类型': '费率'})
                        for flavor in ratingSummaryDetail.flavor:
                            temp_instance_flavor_data.append({"  " + flavor.flavor_name: flavor.rate})
                else:
                    temp_non_instance_data.append({ratingSummaryDetail.service:ratingSummaryDetail.total})

            # 整合所有数据
            if temp_non_instance_data is not None:
                temp_data.extend(temp_non_instance_data)
            if temp_instance_flavor_data is not None:
                temp_data.extend(temp_instance_flavor_data)
            if temp_total_rating_data is not None:
                temp_data.extend(temp_total_rating_data)
            # print(f"整合后的数据：{temp_data}")
            return temp_data
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"生成PDF数据: {e}")

    def create_rating_summary_detail_pdf_with_table(self, input_data, filename):
        try:
            # 转换数据为二维数组
            table_data = [[list(item.keys())[0], list(item.values())[0]] for item in input_data]

            # 创建PDF文档
            doc = SimpleDocTemplate(filename, pagesize=A4)

            if platform.system() == "Windows":
                # 注册中文字体
                pdfmetrics.registerFont(TTFont('SimSun', 'simsun.ttc'))
                font_name = 'SimSun'
                print(f"system: {platform.system()}, font_name: {font_name}")
            else:
                try:
                    # 尝试注册系统可能存在的中文字体
                    pdfmetrics.registerFont(TTFont('SimSun', '/usr/share/fonts/chinese/simsun.ttc'))
                    font_name = 'SimSun'
                    print(f"system: {platform.system()}, font_name: {font_name}")
                except Exception as e:
                    font_name = 'Helvetica'
                    print(f"system: {platform.system()}, font_name: {font_name}")
                    import traceback
                    traceback.print_exc()
            print(f"registered font:{pdfmetrics.getRegisteredFontNames()}, font_name:{font_name}")
            # 定义表格样式（包含列宽设置）
            col_widths = [150, 200]  # 第一列150pt，第二列250pt
            table = Table(table_data, colWidths=col_widths)
            table.setStyle([('FONTNAME', (0, 0), (-1, -1), font_name)])  # 设置字体
            table.setStyle([('ALIGN', (0, 0), (-1, -1), 'LEFT')]) # 靠左对齐
            table.setStyle([('GRID', (0, 0), (-1, -1), 1, colors.black)])  # 添加网格线

            # 构建PDF
            doc.build([table])
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"生成PDF[{filename}]失败: {e}")