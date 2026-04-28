"""
Excel导出模块 —— "表格生成器"
==========================
功能：把候选人数据导出成Excel文件

原理：
- 用 openpyxl 库创建 Excel 工作簿
- 生成两个Sheet："推荐台账" 和 "淘汰台账"
- 每个Sheet里有表头（姓名、电话、学校等）和数据行
- 可以选是否包含评分详情、沟通情况

Excel是什么？
简单来说就是"电子表格"，像你在电脑上看到的 .xlsx 文件，
可以打开、编辑、发送给别人。
"""

import os
from datetime import datetime
from typing import List, Dict

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment


class ExcelExporter:
    """
    Excel导出器

    用法示例：
        exporter = ExcelExporter()
        filepath = exporter.export(candidates, include_scores=True)
        print(f"Excel已生成：{filepath}")
    """

    # ========== 列配置 ==========
    # "推荐台账"用的列
    RECOMMEND_COLUMNS = [
        "序号", "岗位", "实习生", "沟通时间", "姓名", "手机号", "邮箱",
        "性别", "出生年", "学校", "专业", "学历", "是否为应届生（2026届）",
        "招聘渠道", "推荐沟通情况", "备注"
    ]

    # "淘汰台账"用的列
    ELIMINATE_COLUMNS = [
        "序号", "实习生", "沟通时间", "姓名", "手机号", "邮箱",
        "性别", "出生年", "学校", "专业", "学历", "是否是应届生（2026届）",
        "招聘渠道", "沟通状态", "沟通详情", "（淘汰模板）"
    ]

    def __init__(self, output_dir: str = "data"):
        """
        初始化导出器

        参数:
            output_dir: Excel文件存放的文件夹，默认是 data/
        """
        self.output_dir = output_dir

        # 如果文件夹不存在，自动创建
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

    def export(self, candidates: List[Dict],
               include_scores: bool = False,
               include_description: bool = True) -> str:
        """
        导出Excel文件

        参数:
            candidates: 候选人列表（从数据库查出来的字典列表）
            include_scores: 是否包含各维度评分列（默认不包含）
            include_description: 是否包含沟通情况列（默认包含）

        返回:
            生成的Excel文件的完整路径

        示例：
            filepath = exporter.export(candidates, include_scores=True)
            # 返回：data/招聘台账_20250427_143052.xlsx
        """
        # 创建工作簿（就是Excel文件）
        wb = Workbook()

        # ===== 第一个Sheet：推荐台账 =====
        ws_recommend = wb.active  # 默认的第一个Sheet
        ws_recommend.title = "推荐台账"
        self._write_sheet(ws_recommend, candidates, "推荐",
                          include_scores, include_description)

        # ===== 第二个Sheet：淘汰台账 =====
        ws_eliminate = wb.create_sheet("淘汰台账")
        self._write_sheet(ws_eliminate, candidates, "淘汰",
                          include_scores, include_description)

        # ===== 保存文件 =====
        # 文件名带时间戳，避免覆盖之前的文件
        filename = f"招聘台账_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = os.path.join(self.output_dir, filename)

        try:
            wb.save(filepath)
        except Exception as e:
            raise RuntimeError(f"保存Excel文件失败：{e}")

        return filepath

    def _write_sheet(self, ws, candidates: List[Dict], result_type: str,
                     include_scores: bool, include_description: bool):
        """
        写入一个Sheet的内容

        参数:
            ws: Sheet对象
            candidates: 所有候选人（会在内部按结果筛选）
            result_type: "推荐" 或 "淘汰"
            include_scores: 是否包含评分
            include_description: 是否包含沟通情况
        """
        # 筛选出对应结果的候选人
        # 比如 result_type="推荐"，就只留 result="推荐" 的人
        filtered = [c for c in candidates if c.get("result") == result_type]

        # 确定用哪套列
        if result_type == "推荐":
            columns = self.RECOMMEND_COLUMNS.copy()
            desc_field = "推荐沟通情况"
        else:
            columns = self.ELIMINATE_COLUMNS.copy()
            desc_field = "沟通详情"

        # 如果需要评分，在末尾加上评分列
        if include_scores:
            score_cols = ["总分", "动机意愿", "销售基础能力", "沟通逻辑",
                          "抗压韧性", "稳定性", "自我驱动力", "价值观归因"]
            columns.extend(score_cols)

        # 如果不需要沟通情况，去掉对应的列
        if not include_description and desc_field in columns:
            columns.remove(desc_field)

        # ===== 写入表头（第一行，加粗居中）=====
        for col_idx, col_name in enumerate(columns, 1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.font = Font(bold=True)  # 加粗
            cell.alignment = Alignment(horizontal='center')  # 居中

        # ===== 写入数据行 =====
        for row_idx, candidate in enumerate(filtered, 2):  # 从第2行开始
            self._write_row(ws, row_idx, candidate, columns, desc_field)

        # ===== 调整列宽 =====
        for col_idx in range(1, len(columns) + 1):
            col_letter = ws.cell(row=1, column=col_idx).column_letter
            ws.column_dimensions[col_letter].width = 15

    def _write_row(self, ws, row_idx: int, candidate: Dict,
                   columns: List[str], desc_field: str):
        """
        写入单行数据

        根据列名，从候选人字典里取出对应的值，填到单元格里。
        """
        for col_idx, col_name in enumerate(columns, 1):
            value = self._get_value(candidate, col_name, desc_field)
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            # 文字自动换行，顶部对齐（方便看多行内容）
            cell.alignment = Alignment(wrap_text=True, vertical='top')

    def _get_value(self, candidate: Dict, col_name: str, desc_field: str):
        """
        获取单元格的值

        这是一个"翻译器"：
        - Excel里的列名是中文（如"姓名"）
        - 候选人字典里的键也是中文（如"name"）
        - 这个方法负责把列名映射到对应的值
        """
        # 基础字段映射
        field_map = {
            "序号": candidate.get("id"),
            "岗位": "销售",
            "实习生": candidate.get("intern_name"),
            "姓名": candidate.get("name"),
            "沟通时间": candidate.get("communicate_time"),
            "手机号": candidate.get("phone"),
            "邮箱": candidate.get("email"),
            "性别": candidate.get("gender"),
            "出生年": candidate.get("birth_year"),
            "学校": candidate.get("school"),
            "专业": candidate.get("major"),
            "学历": candidate.get("education"),
            "是否为应届生": candidate.get("is_fresh_grad"),
            "是否为应届生（2026届）": candidate.get("is_fresh_grad"),
            "是否是应届生（2026届）": candidate.get("is_fresh_grad"),
            "招聘渠道": candidate.get("channel"),
            "推荐沟通情况": candidate.get("description"),
            "沟通详情": candidate.get("description"),
            "沟通状态": candidate.get("result") or "待审核",
            "备注": candidate.get("remarks") or "",
            "（淘汰模板）": "",
            "总分": candidate.get("score_total")
        }

        # 评分维度（从 score_details 字典里取）
        if col_name in ["动机意愿", "销售基础能力", "沟通逻辑",
                        "抗压韧性", "稳定性", "自我驱动力", "价值观归因"]:
            scores = candidate.get("score_details", {})
            return scores.get(col_name, "")

        return field_map.get(col_name, "")
