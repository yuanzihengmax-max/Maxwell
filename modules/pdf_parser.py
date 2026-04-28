"""
PDF解析模块 —— "简历阅读机器人"
==============================
功能：读取PDF简历，自动提取里面的关键信息

原理：
- PDF本质上是"图片+文字"，pdfplumber 帮我们把里面的文字提取出来
- 提取出全部文字后，用正则表达式（一种文字匹配规则）找出姓名、电话、学校等
- 比如手机号是 1 开头 + 10位数字，就能用规则自动找出来
"""

import os
import re
import tempfile
from typing import Dict, Optional, Union

import pdfplumber


class PDFParser:
    """
    简历PDF解析器

    用法示例：
        parser = PDFParser()
        info = parser.parse_resume("/path/to/resume.pdf")
        print(info["name"])   # 输出姓名
        print(info["phone"])  # 输出手机号
    """

    def extract_text(self, pdf_source: Union[str, object]) -> str:
        """
        从PDF中提取全部文字

        参数:
            pdf_source: 可以是文件路径（字符串），也可以是文件对象
                        这样既能直接读电脑上的文件，也能处理网页上传的文件

        返回:
            PDF里的所有文字，拼成一个大字符串
        """
        text = ""
        try:
            with pdfplumber.open(pdf_source) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            raise RuntimeError(f"PDF解析失败，可能是文件损坏或不是PDF格式: {e}")
        return text

    def parse_resume(self, pdf_source: Union[str, object]) -> Dict:
        """
        解析简历，提取结构化信息

        参数:
            pdf_source: PDF文件的路径或文件对象

        返回:
            一个字典，包含提取出的所有信息：
            {
                "name": "张三",
                "phone": "13800138000",
                "email": "zhangsan@email.com",
                "gender": "男",
                "birth_year": 1998,
                "school": "北京大学",
                "major": "计算机科学",
                "education": "本科（全日制）",
                "is_fresh_grad": "否",
                "raw_text": "...简历全部原文..."
            }
            如果某项没提取到，对应的值就是 None 或 ""
        """
        text = self.extract_text(pdf_source)

        return {
            "name": self._extract_name(text),
            "phone": self._extract_phone(text),
            "email": self._extract_email(text),
            "gender": self._extract_gender(text),
            "birth_year": self._extract_birth_year(text),
            "school": self._extract_school(text),
            "major": self._extract_major(text),
            "education": self._extract_education(text),
            "is_fresh_grad": self._check_fresh_grad(text),
            "raw_text": text  # 保留原文，后面AI分析时要用
        }

    # ========== 信息提取方法 ==========

    def _extract_phone(self, text: str) -> Optional[str]:
        """提取手机号（中国大陆）

        规则：1 开头，第二位是 3-9 之间的数字，后面跟9位数字
        例如：13800138000
        """
        pattern = r'1[3-9]\d{9}'
        match = re.search(pattern, text)
        return match.group() if match else None

    def _extract_email(self, text: str) -> Optional[str]:
        """提取邮箱地址

        规则：xxx@xxx.xxx 的格式
        """
        pattern = r'[\w.-]+@[\w.-]+\.\w+'
        match = re.search(pattern, text)
        return match.group() if match else None

    def _extract_birth_year(self, text: str) -> Optional[int]:
        """提取出生年份

        支持格式：1998年、1998-、1998.、1998/、出生年月：1998、2001.09 等
        年份范围限制在 1970-2010 之间
        """
        patterns = [
            r'出生[日期年月]?[\s:：]+(19\d{2}|20\d{2})',
            r'(19\d{2}|20\d{2})年\s*\d{1,2}\s*月',
            r'(19\d{2}|20\d{2})年',
            r'(19\d{2}|20\d{2})[-./]\d{2}',
            r'(19\d{2}|20\d{2})[-./]',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                year = int(match.group(1))
                if 1970 <= year <= 2010:
                    return year
        return None

    def _extract_gender(self, text: str) -> Optional[str]:
        """推断性别

        规则：看简历里有没有 "男"、"先生"、"女"、"女士" 这些词
        """
        if re.search(r'男|先生', text):
            return "男"
        elif re.search(r'女|女士', text):
            return "女"
        return None

    def _extract_name(self, text: str) -> Optional[str]:
        """提取姓名

        规则：
        1. 看简历前10行（姓名通常在开头）
        2. 找2-4个中文字符（中国人姓名通常这个长度）
        3. 排除一些常见的非姓名词汇（如"简历"、"求职"等）

        注意：这个方法是"规则猜测"，不一定100%准确。
        如果提取错了，后面还可以用AI来修正。
        """
        lines = text.strip().split('\n')

        # 常见干扰词，这些不是人名
        excluded = {
            '简历', '求职', '应聘', '个人', '基本信息', '联系方式',
            '教育背景', '工作经历', '自我评价', '专业技能',
            '姓名', '电话', '邮箱', '学校', '专业'
        }

        for line in lines[:10]:
            line = line.strip()

            # 长度检查：2-4个字符
            if not (2 <= len(line) <= 4):
                continue

            # 必须全是中文字符（允许中间有"·"，比如"艾力·买买提"）
            if not re.match(r'^[一-龥·]+$', line):
                continue

            # 排除干扰词
            if line in excluded:
                continue

            return line

        return None

    def _extract_school(self, text: str) -> Optional[str]:
        """提取学校名称

        规则：匹配 "xx大学"、"xx学院"、"xx学校"
        """
        patterns = [
            r'([一-龥]+大学)',
            r'([一-龥]+学院)',
            r'([一-龥]+学校)'
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def _extract_major(self, text: str) -> Optional[str]:
        """提取专业名称

        规则：匹配 "专业：计算机科学" 或 "计算机科学专业"
        """
        patterns = [
            r'专业[：:]\s*([一-龥]+)',
            r'([一-龥]+专业)'
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                # 去掉末尾的"专业"两个字
                return match.group(1).replace('专业', '')
        return None

    def _extract_education(self, text: str) -> Optional[str]:
        """提取学历

        规则：在文本里找"本科"、"硕士"、"大专"、"专科"等关键词
        然后映射成标准化的学历名称
        """
        edu_map = {
            "本科": "本科（全日制）",
            "硕士": "硕士",
            "研究生": "硕士",
            "大专": "专科（全日制）",
            "专科": "专科（全日制）"
        }
        for key, value in edu_map.items():
            if key in text:
                return value
        return None

    def _check_fresh_grad(self, text: str) -> str:
        """判断是否为应届生

        规则：
        1. 看有没有"应届"、"20xx届"这些关键词
        2. 也检查毕业年份，如果是当前年份或明年，也算应届生
        """
        from datetime import datetime
        current_year = datetime.now().year
        next_year = current_year + 1

        # 匹配 "2025届"、"2026届" 或 "应届"
        year_pattern = rf'{current_year}届|{next_year}届|应届'
        if re.search(year_pattern, text):
            return "是"

        # 匹配独立的年份数字（如"2026"）
        if re.search(rf'{current_year}|{next_year}', text):
            return "是"

        return "否"
