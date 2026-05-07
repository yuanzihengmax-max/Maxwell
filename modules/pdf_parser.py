"""
PDF解析模块 —— "简历阅读机器人"
==============================
功能：读取PDF简历，自动提取里面的关键信息

原理：
- PDF本质上是"图片+文字"，pdfplumber 帮我们把里面的文字提取出来
- 提取出全部文字后，用正则表达式（一种文字匹配规则）找出姓名、电话、学校等
- 比如手机号是 1 开头 + 10位数字，就能用规则自动找出来
"""

import base64
import io
import os
import re
import tempfile
from typing import Dict, Optional, Tuple, Union

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

    def parse_resume(self, pdf_source: Union[str, object], ai_analyzer=None) -> Dict:
        """
        解析简历，提取结构化信息

        参数:
            pdf_source: PDF文件的路径或文件对象
            ai_analyzer: AI分析器实例（用于照片性别识别fallback）

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

        result = {
            "name": self._extract_name(text),
            "phone": self._extract_phone(text),
            "email": self._extract_email(text),
            "gender": self._extract_gender(text, pdf_source, ai_analyzer),
            "birth_year": self._extract_birth_year(text),
            "school": self._extract_school(text),
            "major": self._extract_major(text),
            "education": self._extract_education(text),
            "is_fresh_grad": self._check_fresh_grad(text),
            "raw_text": text  # 保留原文，后面AI分析时要用
        }

        # 按需 AI fallback：姓名/手机号/邮箱/出生年份任一为空时调用AI补充
        if ai_analyzer and (not result.get("name") or not result.get("phone") or not result.get("email") or not result.get("birth_year")):
            try:
                missing = ai_analyzer.extract_missing_info(text)
                if missing and isinstance(missing, dict):
                    if not result.get("name") and missing.get("name"):
                        result["name"] = missing["name"]
                    if not result.get("phone") and missing.get("phone"):
                        result["phone"] = missing["phone"]
                    if not result.get("email") and missing.get("email"):
                        result["email"] = missing["email"]
                    if not result.get("birth_year") and missing.get("birth_year"):
                        try:
                            by = missing["birth_year"]
                            if isinstance(by, int) and 1960 <= by <= 2015:
                                result["birth_year"] = by
                            elif isinstance(by, str) and by.isdigit():
                                by_int = int(by)
                                if 1960 <= by_int <= 2015:
                                    result["birth_year"] = by_int
                        except (ValueError, TypeError):
                            pass
            except Exception:
                # AI fallback 失败时不阻断主流程
                pass

        return result

    # ========== 信息提取方法 ==========

    def _extract_phone(self, text: str) -> Optional[str]:
        """提取手机号（中国大陆）

        规则：
        1. 优先匹配带前缀格式（手机/电话/Tel/Mobile）
        2. 支持空格、横杠、括号等分隔符
        3. 清洗后验证 1 开头 + 10 位数字
        """
        # 策略1：匹配带前缀的号码（允许空格、横杠、括号）
        prefix_pattern = r'(?:手机|电话|Tel|Mobile|联系方式)[\s:：]*([0-9\s\-()]{11,20})'
        match = re.search(prefix_pattern, text, re.IGNORECASE)
        if match:
            cleaned = re.sub(r'[\s\-\()]', '', match.group(1))
            if re.fullmatch(r'1[3-9]\d{9}', cleaned):
                return cleaned

        # 策略2：直接匹配 11 位手机号（允许中间有空格/横杠）
        broad_pattern = r'1[3-9]\d[\s\-]?\d{4}[\s\-]?\d{4}'
        match = re.search(broad_pattern, text)
        if match:
            cleaned = re.sub(r'[\s\-]', '', match.group())
            if re.fullmatch(r'1[3-9]\d{9}', cleaned):
                return cleaned

        # 策略3：纯数字直接匹配
        match = re.search(r'1[3-9]\d{9}', text)
        if match:
            return match.group()

        return None

    def _extract_email(self, text: str) -> Optional[str]:
        """提取邮箱地址

        规则：
        1. 支持标准格式 xxx@xxx.xxx
        2. 支持 @ 前后有空格/换行的情况
        3. 增强域名后缀匹配
        """
        # 策略1：允许 @ 前后有空格或换行
        pattern = r'[\w.-]+\s*@\s*[\w.-]+\.\w+'
        match = re.search(pattern, text)
        if match:
            return re.sub(r'\s+', '', match.group())

        # 策略2：处理换行断开的邮箱（把文本中的换行替换为空格后重试）
        normalized = text.replace('\n', ' ').replace('\r', ' ')
        match = re.search(r'[\w.-]+@[\w.-]+\.\w+', normalized)
        if match:
            return match.group()

        return None

    def _extract_birth_year(self, text: str) -> Optional[int]:
        """提取出生年份

        支持格式：
        - 1998年、1998-、1998.、1998/、出生年月：1998、2001.09 等
        - 18位身份证号
        - 出生年月日完整日期格式
        年份范围限制在 1960-2015 之间（覆盖更宽的年龄段）
        """
        patterns = [
            r'出生[日期年月]?[\s:：]+(19\d{2}|20\d{2})',
            r'(19\d{2}|20\d{2})年\s*\d{1,2}\s*月',
            r'(19\d{2}|20\d{2})年',
            r'(19\d{2}|20\d{2})[-./]\d{2}',
            r'(19\d{2}|20\d{2})[-./]',
            # 纯数字年份（前后有换行或空格，避免误匹配其他4位数字）
            r'(?:^|\s|\n)(19[6-9]\d|20[0-1]\d)(?:\s|\n|$)',
            # 出生年月日完整格式，只取年份
            r'(?:出生)?[日期年月\s]*[\s:：]*(19\d{2}|20\d{2})[年./\s]*\d{1,2}[月./\s]*\d{1,2}',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                year = int(match.group(1))
                if 1960 <= year <= 2015:
                    return year

        # 从18位身份证号提取出生年份
        id_match = re.search(r'(\d{6})(19\d{2}|20\d{2})(\d{4})(?:\d|[Xx])', text)
        if id_match:
            year = int(id_match.group(2))
            if 1960 <= year <= 2015:
                return year

        # Fallback: 通过教育阶段推算
        inferred = self._infer_birth_year_from_education(text)
        if inferred:
            return inferred

        return None

    def _extract_gender(self, text: str, pdf_source=None, ai_analyzer=None) -> Optional[str]:
        """推断性别

        规则：
        1. 优先匹配 "性别：男/女" 等标准格式
        2. 再回退到 "男"、"先生"、"女"、"女士" 等关键词
        3. 最后fallback：AI照片识别（仅当pdf_source和ai_analyzer都提供时）
        """
        # 优先匹配标准格式：性别：男 / 性别:女 / 性别 男
        explicit = re.search(r'性别[\s:：]*(男|女)', text)
        if explicit:
            return explicit.group(1)
        if re.search(r'男|先生', text):
            return "男"
        elif re.search(r'女|女士', text):
            return "女"

        # Fallback: AI 照片识别
        if pdf_source and ai_analyzer:
            photo = self._extract_photo_base64(pdf_source)
            if photo:
                return self._infer_gender_from_photo(photo, ai_analyzer)
            else:
                # 照片提取失败，记录提示供上层展示
                try:
                    import streamlit as st
                    if "_photo_extract_error" not in st.session_state:
                        st.session_state["_photo_extract_error"] = "未能在PDF中找到照片，性别将跳过照片识别。"
                except Exception:
                    pass

        return None

    # ========== 照片提取 & AI 性别识别 ==========

    def _extract_photo_base64(self, pdf_source: Union[str, object]) -> Optional[Tuple[str, str]]:
        """从PDF第一页提取证件照，转为base64

        策略：
        1. 先尝试提取PDF中嵌入的图片对象（精确裁剪）
        2. 如果失败，渲染整页并裁剪顶部区域作为 fallback

        返回: (mime_type, base64_data) 或 None
        """
        try:
            from PIL import Image
        except ImportError:
            return None

        try:
            with pdfplumber.open(pdf_source) as pdf:
                if not pdf.pages:
                    return None
                page = pdf.pages[0]

                # 策略1：提取嵌入的图片
                embedded = self._extract_embedded_images(page)
                if embedded:
                    best = max(embedded, key=lambda c: c["score"])
                    return ("image/jpeg", best["b64"])

                # 策略2：渲染页面顶部区域
                rendered = self._extract_from_page_render(page)
                if rendered:
                    return rendered

        except Exception as e:
            try:
                import streamlit as st
                st.session_state["_photo_extract_error"] = f"照片提取失败: {str(e)}"
            except Exception:
                pass

        return None

    def _extract_embedded_images(self, page) -> list:
        """从PDF页面中提取嵌入的图片对象（更宽松的过滤条件）"""
        try:
            page_image = page.to_image(resolution=150)
            pil_page = page_image.original
        except Exception:
            return []

        candidates = []
        if not page.images:
            return candidates

        for img in page.images:
            w = img.get("width", 0)
            h = img.get("height", 0)
            top = img.get("top", 0)
            page_h = page.height

            # 更宽松的尺寸范围
            if not (20 <= w <= 300 and 30 <= h <= 350):
                continue

            # 更宽松的位置：照片可以在页面任何位置，但顶部权重更高
            position_score = 1.0 if top < page_h * 0.3 else (0.5 if top < page_h * 0.6 else 0.2)

            # 更宽松的宽高比
            ratio = w / h if h > 0 else 0
            if not (0.4 <= ratio <= 1.2):
                continue

            try:
                bbox = (img["x0"], img["top"], img["x1"], img["bottom"])
                px_bbox = page_image._reproject_bbox(bbox)
                cropped = pil_page.crop(px_bbox)

                if cropped.mode != "RGB":
                    cropped = cropped.convert("RGB")
                buf = io.BytesIO()
                cropped.save(buf, format="JPEG", quality=85)
                b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

                area = w * h
                area_score = 1 / (1 + abs(area - 6000) / 6000)
                ratio_score = 1 - abs(ratio - 0.75) / 0.35

                score = area_score * 0.35 + position_score * 0.35 + ratio_score * 0.3

                candidates.append({
                    "b64": b64,
                    "score": score,
                })
            except Exception:
                continue

        return candidates

    def _extract_from_page_render(self, page) -> Optional[Tuple[str, str]]:
        """渲染页面并裁剪顶部区域作为照片提取 fallback"""
        try:
            from PIL import Image
            page_image = page.to_image(resolution=150)
            pil_page = page_image.original
            w, h = pil_page.size

            # 裁剪页面顶部 35% 区域（简历照片通常在此）
            crop_box = (0, 0, w, int(h * 0.35))
            cropped = pil_page.crop(crop_box)

            if cropped.mode != "RGB":
                cropped = cropped.convert("RGB")

            # 缩放到合理尺寸以减少传输量
            max_dim = 800
            if max(cropped.size) > max_dim:
                ratio = max_dim / max(cropped.size)
                new_size = (int(cropped.size[0] * ratio), int(cropped.size[1] * ratio))
                cropped = cropped.resize(new_size, Image.Resampling.LANCZOS)

            buf = io.BytesIO()
            cropped.save(buf, format="JPEG", quality=80)
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            return ("image/jpeg", b64)
        except Exception:
            return None

    def _infer_gender_from_photo(self, photo_b64: Tuple[str, str], ai_analyzer) -> Optional[str]:
        """调用AI服务识别照片中的性别

        参数:
            photo_b64: (mime_type, base64_data) 元组
            ai_analyzer: AIAnalyzer 实例

        返回: "男" / "女" / None
        """
        if ai_analyzer is None or ai_analyzer.client is None:
            return None

        mime_type, b64_data = photo_b64
        try:
            from openai import APIError
            response = ai_analyzer.client.chat.completions.create(
                model=ai_analyzer.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": '这是一张简历中的照片或简历页面截图。请判断照片中人物的性别，只回答"男"或"女"。如果这不是人脸照片或无法判断，请回答"未知"。'
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}
                            }
                        ]
                    }
                ],
                max_tokens=50,
                temperature=0.0
            )
            content = response.choices[0].message.content.strip()

            # 记录 API 用量
            if ai_analyzer.db and hasattr(response, "usage") and response.usage:
                try:
                    from config import calculate_cost
                    pt = response.usage.prompt_tokens or 0
                    ct = response.usage.completion_tokens or 0
                    cost = calculate_cost(ai_analyzer.model, pt, ct)
                    ai_analyzer.db.log_api_usage(
                        feature="photo_gender",
                        model=ai_analyzer.model,
                        prompt_tokens=pt,
                        completion_tokens=ct,
                        estimated_cost=cost,
                    )
                except Exception:
                    pass

            if "男" in content and "女" not in content:
                return "男"
            elif "女" in content and "男" not in content:
                return "女"
            return None
        except APIError as e:
            err_msg = str(e).lower()
            if any(k in err_msg for k in ("vision", "image", "multimodal", "content type", "invalid content")):
                try:
                    import streamlit as st
                    st.session_state["_gender_vision_error"] = (
                        f"当前模型 '{ai_analyzer.model}' 不支持图片识别，"
                        f"性别识别失败。建议切换到支持 vision 的模型，"
                        f"如 Qwen/Qwen3-VL-8B-Instruct 或 gpt-4o-mini。"
                    )
                except Exception:
                    pass
            else:
                try:
                    import streamlit as st
                    st.session_state["_gender_vision_error"] = f"照片性别识别 API 错误：{e}"
                except Exception:
                    pass
            return None
        except Exception as e:
            try:
                import streamlit as st
                st.session_state["_gender_vision_error"] = f"照片性别识别出错：{e}"
            except Exception:
                pass
            return None

    # ========== 出生年份推算（教育阶段） ==========

    def _infer_birth_year_from_education(self, text: str) -> Optional[int]:
        """通过教育时间段推算出生年份

        规则：
        - 本科毕业年份 - 22 = 出生年（假设6岁入学）
        - 硕士毕业年份 - 25 = 出生年
        - 优先用本科推算（入学年龄更集中，误差更小）
        """
        lines = text.split("\n")

        # 1. 优先找本科相关行
        for line in lines:
            if "本科" in line or "大学" in line or "学士" in line:
                # 匹配格式：2022.09-2026.06 或 2022-2026 或 2022.09~2026.06
                m = re.search(r'(\d{4})[\.\-/年]\d{1,2}.*?[-~至—]\s*(\d{4})', line)
                if m:
                    grad_year = int(m.group(2))
                    birth = grad_year - 22
                    if 1980 <= birth <= 2010:
                        return birth
                # 简化格式：2022-2026（无月份）
                m = re.search(r'(\d{4})\s*[-~至—]\s*(\d{4})', line)
                if m:
                    grad_year = int(m.group(2))
                    birth = grad_year - 22
                    if 1980 <= birth <= 2010:
                        return birth

        # 2. 再找硕士相关行
        for line in lines:
            if "硕士" in line or "研究生" in line:
                m = re.search(r'(\d{4})[\.\-/年]\d{1,2}.*?[-~至—]\s*(\d{4})', line)
                if m:
                    grad_year = int(m.group(2))
                    birth = grad_year - 25
                    if 1980 <= birth <= 2010:
                        return birth
                m = re.search(r'(\d{4})\s*[-~至—]\s*(\d{4})', line)
                if m:
                    grad_year = int(m.group(2))
                    birth = grad_year - 25
                    if 1980 <= birth <= 2010:
                        return birth

        return None

    def _extract_name(self, text: str) -> Optional[str]:
        """提取姓名

        策略：
        1. 优先从"姓名"标签行提取（如"姓名：张三"）
        2. 在前15行中找2-4个纯中文字符，排除已知非人名词
        3. 如果某行附近（前后2行）有手机号或邮箱，该行更可能是姓名

        注意：这个方法是"规则猜测"，不一定100%准确。
        如果提取错了，后面还可以用AI来修正。
        """
        lines = text.strip().split('\n')

        # 常见干扰词，这些不是人名
        excluded = {
            '简历', '求职', '应聘', '个人', '基本信息', '联系方式',
            '教育背景', '工作经历', '自我评价', '专业技能', '项目经验',
            '姓名', '电话', '邮箱', '学校', '专业', '学历', '性别', '年龄',
            '籍贯', '民族', '政治面貌', '身高', '体重', '婚姻', '现居',
            '期望', '薪资', '待遇', '到岗', '时间', '意向', '岗位', '职位',
            '面试', '招聘', '人力', '资源', '行政', '财务', '销售', '市场',
            '运营', '技术', '研发', '设计', '测试', '运维', '产品', '管理',
            '经理', '主管', '总监', '助理', '专员', '工程师', '顾问', '教师',
            '医生', '律师', '会计', '出纳', '翻译', '秘书', '司机', '编辑',
            '记者', '北京', '上海', '广州', '深圳', '杭州', '成都', '南京',
            '武汉', '西安', '重庆', '天津', '苏州', '长沙', '郑州', '东莞',
            '青岛', '宁波', '无锡', '佛山', '合肥', '大连', '厦门', '济南',
            '先生', '小姐', '女士',
        }

        # 策略1：优先从"姓名"标签行提取（支持同一行或跨行）
        for i, line in enumerate(lines[:50]):
            line_stripped = line.strip()
            # 1a: 标签和名字在同一行
            m = re.search(r'(?:姓名|Name)[\s:：]+([一-龥a-zA-Z·\s]{2,10})', line_stripped, re.IGNORECASE)
            if m:
                name = m.group(1).strip()
                # 提取其中的中文部分
                cn_only = re.findall(r'[一-龥·]+', name)
                if cn_only:
                    candidate = ''.join(cn_only)
                    if 2 <= len(candidate) <= 4:
                        return candidate
            # 1b: 标签单独一行，名字在下一行
            if re.match(r'^(?:姓名|Name)[\s:：]*$', line_stripped, re.IGNORECASE):
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if re.match(r'^[一-龥·]+$', next_line) and 2 <= len(next_line) <= 4:
                        if next_line not in excluded:
                            return next_line

        # 策略2：前50行找纯中文2-4字，带上下文判断
        candidates = []
        for i, line in enumerate(lines[:50]):
            line = line.strip()

            # 长度检查：2-4个字符
            if not (2 <= len(line) <= 4):
                continue

            # 必须全是中文字符（允许中间有"·"）
            if not re.match(r'^[一-龥·]+$', line):
                continue

            # 排除干扰词
            if line in excluded:
                continue

            # 排除包含机构/公司/学校后缀的词
            if any(suffix in line for suffix in ['公司', '集团', '企业', '科技', '工作室', '协会', '大学', '学院', '学校', '研究院', '研究所', '中心']):
                continue

            # 如果附近（前后2行）有手机号或邮箱，置信度高，直接返回
            nearby = '\n'.join(lines[max(0, i - 1):min(len(lines), i + 3)])
            if re.search(r'1[3-9]\d{9}', nearby) or '@' in nearby:
                return line

            candidates.append(line)

        # 回退：返回第一个没有上下文信号的候选
        if candidates:
            return candidates[0]

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

        规则：
        1. 优先匹配 "专业：xxx" 或 "专业 xxx" 格式
        2. 再尝试匹配 "xxx专业"
        3. 最后回退到常见专业词库匹配
        """
        # 常见专业词库（用于回退匹配）
        # 教育部《普通高等学校本科专业目录（2026年）》完整专业名录（共882个）
        common_majors = [
            "野生动物与自然保护区管理",
            "飞行器环境与生命保障工程",
            "食品药品环境犯罪侦查技术",
            "信用风险管理与法律防控",
            "农业建筑环境与能源工程",
            "化学工程与工业生物工程",
            "大功率半导体科学与工程",
            "建筑环境与能源应用工程",
            "无人驾驶航空器系统工程",
            "机械设计制造及其自动化",
            "集成电路设计与集成系统",
            "中国少数民族语言文学",
            "农业机械化及其自动化",
            "婴幼儿发展与健康管理",
            "数据科学与大数据技术",
            "水土保持与荒漠化防治",
            "飞行器控制与信息工程",
            "交通设备与控制工程",
            "人居环境科学与技术",
            "人文地理与城乡规划",
            "作曲与作曲技术理论",
            "信息管理与信息系统",
            "光电信息材料与器件",
            "光电信息科学与工程",
            "医疗器械与装备工程",
            "国家公园建设与管理",
            "国际事务与国际关系",
            "国际组织与全球治理",
            "地球信息科学与技术",
            "外国语言与外国历史",
            "应急装备技术与工程",
            "弹药工程与爆炸技术",
            "抢险救援指挥与技术",
            "探测制导与控制技术",
            "数据资源与数据智能",
            "旅游地学与规划工程",
            "旅游管理与服务教育",
            "无机非金属材料工程",
            "智慧城市与空间规划",
            "智慧牧业科学与工程",
            "智能工程与创意设计",
            "智能建造与智慧交通",
            "服装设计与工艺教育",
            "材料成型及控制工程",
            "材料设计科学与工程",
            "核化工与核燃料工程",
            "核电技术与控制工程",
            "武术与民族传统体育",
            "海洋智能与无人技术",
            "海洋渔业科学与技术",
            "海警舰艇指挥与技术",
            "港口航道与海岸工程",
            "特种能源技术与工程",
            "珠宝首饰设计与工艺",
            "生物农药科学与工程",
            "电子信息科学与技术",
            "电子竞技运动与管理",
            "电气工程与智能控制",
            "电气工程及其自动化",
            "社会体育指导与管理",
            "稀土材料科学与工程",
            "空天智能电推进技术",
            "空间信息与数字技术",
            "粉体材料科学与工程",
            "纤维科学与智能制造",
            "能源与环境系统工程",
            "自然地理与资源环境",
            "自然资源登记与管理",
            "航空服务艺术与管理",
            "设施农业科学与工程",
            "资源循环科学与工程",
            "资源环境大数据工程",
            "轨道交通信号与控制",
            "轨道交通电气与控制",
            "过程装备与控制工程",
            "道路桥梁与渡河工程",
            "防灾减灾科学与工程",
            "集成电路科学与工程",
            "非物质文化遗产保护",
            "飞行器质量与可靠性",
            "食品营养与检验教育",
            "香料香精技术与工程",
            "中草药栽培与鉴定",
            "交通能源融合工程",
            "农业智能装备工程",
            "农林智能装备工程",
            "化妆品技术与工程",
            "化妆品科学与技术",
            "化学测量学与技术",
            "半导体工艺与装备",
            "历史建筑保护工程",
            "听力与言语康复学",
            "国际经济发展合作",
            "地下水科学与工程",
            "地理空间信息工程",
            "城市地下空间工程",
            "复合材料成型工程",
            "大数据管理与应用",
            "宝石及材料工艺学",
            "应用电子技术教育",
            "建筑电气与智能化",
            "微电子科学与工程",
            "戏剧影视美术设计",
            "房地产开发与管理",
            "新能源材料与器件",
            "新能源科学与工程",
            "智能无人系统技术",
            "智能电网信息工程",
            "木结构建筑与材料",
            "水文与水资源工程",
            "汽车维修工程教育",
            "海关检验检疫安全",
            "海洋资源开发技术",
            "生物医药数据科学",
            "生物质技术与工程",
            "生物质科学与工程",
            "生物质能源与材料",
            "电子与计算机工程",
            "电磁场与无线技术",
            "盐碱地科学与工程",
            "碳中和科学与工程",
            "给排水科学与工程",
            "船舶电子电气工程",
            "葡萄与葡萄酒工程",
            "计算机科学与技术",
            "资源与环境经济学",
            "软物质科学与工程",
            "辐射防护与核安全",
            "非织造材料与工程",
            "飞行器设计与工程",
            "食品卫生与营养学",
            "食用菌科学与工程",
            "高分子材料与工程",
            "丝绸设计与工程",
            "中国共产党历史",
            "中国语言与文化",
            "中药资源与开发",
            "中西医临床医学",
            "人才发展与管理",
            "仿生科学与工程",
            "会展经济与管理",
            "低空技术与工程",
            "低空经济与管理",
            "体育经济与管理",
            "信息与计算科学",
            "健康与医疗保障",
            "健康服务与管理",
            "健康科学与技术",
            "储能科学与工程",
            "农业资源与环境",
            "分子科学与工程",
            "劳动与社会保障",
            "勘查技术与工程",
            "化学工程与工艺",
            "卫生检验与检疫",
            "咖啡科学与工程",
            "国际新闻与传播",
            "国际经济与贸易",
            "土地科学与技术",
            "城市水系统工程",
            "复合材料与工程",
            "孤独症儿童教育",
            "家具设计与工程",
            "密码科学与技术",
            "库克群岛毛利语",
            "应急技术与管理",
            "影视摄影与制作",
            "微机电系统工程",
            "播音与主持艺术",
            "政治学与行政学",
            "救助与打捞工程",
            "数学与应用数学",
            "数据计算及应用",
            "文物与博物馆学",
            "文物保护与修复",
            "新能源汽车工程",
            "智慧建筑与建造",
            "智能材料与结构",
            "智能科学与技术",
            "智能装备与系统",
            "智能飞行器技术",
            "服务科学与工程",
            "服装与服饰设计",
            "服装设计与工程",
            "木材科学与工程",
            "材料科学与工程",
            "核工程与核技术",
            "植物科学与技术",
            "武器系统与工程",
            "气象技术与工程",
            "氢能科学与工程",
            "水利科学与工程",
            "水族科学与技术",
            "水质科学与技术",
            "测控技术与仪器",
            "海洋工程与技术",
            "海洋科学与技术",
            "海洋资源与环境",
            "深地科学与工程",
            "湿地保护与恢复",
            "烹饪与营养教育",
            "焊接技术与工程",
            "环境科学与工程",
            "理论与应用力学",
            "电信工程及管理",
            "电子商务及法律",
            "电子科学与技术",
            "电机电器智能化",
            "电波传播与天线",
            "真空工程与技术",
            "碳储科学与工程",
            "种子科学与工程",
            "稀土科学与工程",
            "空间科学与技术",
            "系统科学与工程",
            "纳米材料与技术",
            "网络安全与执法",
            "老年医学与健康",
            "能源与动力工程",
            "能源互联网工程",
            "能源科学与工程",
            "脑机科学与技术",
            "船舶与海洋工程",
            "草坪科学与工程",
            "药物经济与管理",
            "菌物科学与工程",
            "警务指挥与战术",
            "认知科学与技术",
            "运动与公共健康",
            "遥感科学与技术",
            "邮轮工程与管理",
            "飞行器制造工程",
            "飞行器动力工程",
            "飞行器运维工程",
            "飞行器适航技术",
            "食品安全与检测",
            "食品科学与工程",
            "食品营养与健康",
            "食品质量与安全",
            "马克思主义理论",
            "马术运动与管理",
            "中医骨伤科学",
            "临床工程技术",
            "交通管理工程",
            "人力资源管理",
            "人工智能教育",
            "低空安全管理",
            "信息对抗技术",
            "信息资源管理",
            "假肢矫形工程",
            "公共事业管理",
            "公安政治工作",
            "公安视听技术",
            "养老服务管理",
            "兽医公共卫生",
            "农业水利工程",
            "农村区域发展",
            "农林经济管理",
            "冰雪舞蹈表演",
            "刑事科学技术",
            "加泰罗尼亚语",
            "化工安全工程",
            "医学信息工程",
            "医学实验技术",
            "医学影像技术",
            "医学检验技术",
            "医疗产品管理",
            "印度尼西亚语",
            "口腔医学技术",
            "商业人工智能",
            "国内安全保卫",
            "国民经济管理",
            "国际经贸规则",
            "国际邮轮管理",
            "土地整治工程",
            "土地资源管理",
            "地球系统科学",
            "地理信息科学",
            "地理国情监测",
            "塔玛齐格特语",
            "增材制造工程",
            "妇幼保健医学",
            "安全生产监管",
            "安全防范工程",
            "市场营销教育",
            "广播电视工程",
            "广播电视编导",
            "应用生物科学",
            "康复作业治疗",
            "康复物理治疗",
            "思想政治教育",
            "戏剧影视导演",
            "戏剧影视文学",
            "提格雷尼亚语",
            "政治安全保卫",
            "数字公共治理",
            "数字媒体技术",
            "数字媒体艺术",
            "数字演艺设计",
            "数据警务技术",
            "数理基础科学",
            "文化产业管理",
            "文物保护技术",
            "斯洛文尼亚语",
            "时空信息工程",
            "智慧景观营造",
            "智慧海洋技术",
            "智慧能源工程",
            "智能交互设计",
            "智能体育工程",
            "智能分子工程",
            "智能制造工程",
            "智能医学工程",
            "智能地球探测",
            "智能影像工程",
            "智能影像艺术",
            "智能感知工程",
            "智能测控工程",
            "智能海洋装备",
            "智能视听工程",
            "智能视觉工程",
            "智能车辆工程",
            "智能运输工程",
            "智能采矿工程",
            "机械工艺技术",
            "机械电子工程",
            "机电技术教育",
            "材料智能技术",
            "武器发射工程",
            "水利水电工程",
            "水生动物医学",
            "汉学与中国学",
            "汉语国际教育",
            "汽车服务工程",
            "油气储运工程",
            "海外利益安全",
            "海外安全管理",
            "海洋信息工程",
            "海洋油气工程",
            "海警后勤管理",
            "消防政治工作",
            "游戏艺术设计",
            "环保设备工程",
            "环境生态工程",
            "生物医学工程",
            "生物医学科学",
            "生物育种技术",
            "生物育种科学",
            "电动载运工程",
            "电子信息工程",
            "电子信息材料",
            "电子封装技术",
            "白酒酿造工程",
            "矿物加工工程",
            "矿物资源工程",
            "科学社会主义",
            "经济犯罪侦查",
            "网络与新媒体",
            "网络空间安全",
            "职业卫生工程",
            "能源化学工程",
            "能源服务工程",
            "航空安防管理",
            "航空航天工程",
            "虚拟现实技术",
            "虚拟空间艺术",
            "装甲车辆工程",
            "视觉传达设计",
            "财务会计教育",
            "质量管理工程",
            "资源勘查工程",
            "资源环境审计",
            "资源环境科学",
            "跨境电子商务",
            "运动人体科学",
            "运动能力开发",
            "量子信息科学",
            "金属材料工程",
            "阿尔巴尼亚语",
            "陶瓷艺术设计",
            "马达加斯加语",
            "中医儿科学",
            "中医养生学",
            "中医康复学",
            "中国古典学",
            "乌兹别克语",
            "互联网金融",
            "亚美尼亚语",
            "供应链管理",
            "保加利亚语",
            "光源与照明",
            "克罗地亚语",
            "克里奥尔语",
            "全球健康学",
            "公共关系学",
            "公安情报学",
            "公安管理学",
            "军事海洋学",
            "农业机器人",
            "农业电气化",
            "出入境管理",
            "动植物检疫",
            "劳动经济学",
            "化学生物学",
            "区块链工程",
            "区域国别学",
            "医学影像学",
            "古典文献学",
            "可持续能源",
            "司法警察学",
            "司法鉴定学",
            "合成生物学",
            "吉尔吉斯语",
            "商务经济学",
            "国家安全学",
            "地球物理学",
            "塞尔维亚语",
            "实验动物学",
            "工程互联网",
            "广播电视学",
            "应用心理学",
            "应用气象学",
            "应用物理学",
            "应用统计学",
            "应用语言学",
            "康复治疗学",
            "恩德贝莱语",
            "技术侦查学",
            "拉脱维亚语",
            "教育康复学",
            "教育技术学",
            "斯洛伐克语",
            "斯瓦希里语",
            "新媒体技术",
            "新媒体艺术",
            "无障碍管理",
            "未来机器人",
            "机器人工程",
            "柔性电子学",
            "标准化工程",
            "核医学工程",
            "核生化消防",
            "格鲁吉亚语",
            "梵语巴利语",
            "比斯拉马语",
            "水产养殖学",
            "汉语言文学",
            "海洋机器人",
            "爱沙尼亚语",
            "物联网工程",
            "生态修复学",
            "生物信息学",
            "生物统计学",
            "白俄罗斯语",
            "眼视光医学",
            "经济与金融",
            "经济动物学",
            "经济统计学",
            "编辑出版学",
            "罗马尼亚语",
            "艺术与科技",
            "艺术设计学",
            "计算语言学",
            "跨媒体艺术",
            "针灸推拿学",
            "阿塞拜疆语",
            "阿姆哈拉语",
            "阿非利卡语",
            "零售业管理",
            "中兽医学",
            "中药制药",
            "临床医学",
            "临床药学",
            "乌克兰语",
            "乌尔都语",
            "乐器智造",
            "乡村治理",
            "乳品工程",
            "交叉工程",
            "交通工程",
            "交通管理",
            "交通运输",
            "产品设计",
            "人居设计",
            "人工智能",
            "人文教育",
            "休闲体育",
            "体育康养",
            "体育教育",
            "体育旅游",
            "体能训练",
            "保密技术",
            "保密管理",
            "信息安全",
            "信息工程",
            "信用管理",
            "僧伽罗语",
            "公共艺术",
            "具身智能",
            "内部审计",
            "农业工程",
            "农艺教育",
            "农药化肥",
            "冰雪运动",
            "冶金工程",
            "创业管理",
            "制药工程",
            "功能材料",
            "动物医学",
            "动物科学",
            "动物药学",
            "劳动关系",
            "劳动教育",
            "包装工程",
            "包装设计",
            "匈牙利语",
            "医疗保险",
            "华文教育",
            "卢旺达语",
            "卢森堡语",
            "卫生教育",
            "卫生监督",
            "印刷工程",
            "反恐警务",
            "口腔医学",
            "古文字学",
            "古生物学",
            "哈萨克语",
            "商务英语",
            "园艺教育",
            "国际商务",
            "国际政治",
            "国际税收",
            "图书馆学",
            "土库曼语",
            "土木工程",
            "土耳其语",
            "地球化学",
            "地理科学",
            "地质工程",
            "城乡规划",
            "城市更新",
            "城市管理",
            "城市设计",
            "基础医学",
            "塔吉克语",
            "塞苏陀语",
            "大气科学",
            "孟加拉语",
            "学前教育",
            "安全工程",
            "实验艺术",
            "家庭教育",
            "导航工程",
            "小学教育",
            "尼泊尔语",
            "工业工程",
            "工业智能",
            "工业设计",
            "工业软件",
            "工商管理",
            "工程力学",
            "工程审计",
            "工程物理",
            "工程管理",
            "工程软件",
            "工程造价",
            "工艺美术",
            "市场营销",
            "希伯来语",
            "库尔德语",
            "应急管理",
            "应用中文",
            "应用化学",
            "康复工程",
            "录音艺术",
            "影视技术",
            "意大利语",
            "慈善管理",
            "戏剧教育",
            "手语翻译",
            "放射医学",
            "数字人文",
            "数字出版",
            "数字戏剧",
            "数字文旅",
            "数字经济",
            "数字贸易",
            "数字金融",
            "数据科学",
            "整合科学",
            "文化遗产",
            "旁遮普语",
            "旅游管理",
            "时尚传播",
            "普什图语",
            "智慧交通",
            "智慧农业",
            "智慧应急",
            "智慧林业",
            "智慧水利",
            "智慧渔业",
            "智能建造",
            "智能计算",
            "机械工程",
            "材料化学",
            "材料物理",
            "林产化工",
            "柬埔寨语",
            "森林保护",
            "森林工程",
            "森林消防",
            "植物保护",
            "水务工程",
            "水声工程",
            "法律英语",
            "泰米尔语",
            "流行舞蹈",
            "流行音乐",
            "测绘工程",
            "海事管理",
            "海关稽查",
            "海关管理",
            "海洋技术",
            "海洋科学",
            "海洋药学",
            "海警执法",
            "涂料工程",
            "消防工程",
            "消防指挥",
            "涉外警务",
            "火灾勘查",
            "爱尔兰语",
            "物业管理",
            "物流工程",
            "物流管理",
            "特殊教育",
            "环境工程",
            "环境科学",
            "环境设计",
            "生物制药",
            "生物制造",
            "生物医学",
            "生物工程",
            "生物技术",
            "生物材料",
            "生物科学",
            "电子商务",
            "电影制作",
            "电缆工程",
            "眼视光学",
            "知识产权",
            "石油工程",
            "社会工作",
            "社会政策",
            "社区矫正",
            "神经科学",
            "科学教育",
            "科技艺术",
            "科摩罗语",
            "移民管理",
            "立陶宛语",
            "管理科学",
            "粮食工程",
            "精密仪器",
            "精神医学",
            "精细化工",
            "索马里语",
            "纤维艺术",
            "约鲁巴语",
            "纪检监察",
            "纺织工程",
            "经济工程",
            "网络工程",
            "美术教育",
            "能源化学",
            "能源经济",
            "舞蹈教育",
            "舞蹈治疗",
            "舞蹈编导",
            "舞蹈表演",
            "航海技术",
            "航空运动",
            "艺术史论",
            "艺术教育",
            "艺术治疗",
            "艺术管理",
            "茨瓦纳语",
            "草业科学",
            "药事管理",
            "药物分析",
            "药物制剂",
            "药物化学",
            "菲律宾语",
            "萨摩亚语",
            "葡萄牙语",
            "融合教育",
            "行政管理",
            "行星科学",
            "西班牙语",
            "警犬技术",
            "计算金融",
            "语言智能",
            "语言科学",
            "财务管理",
            "贸易经济",
            "资产评估",
            "资源化学",
            "足球运动",
            "车辆工程",
            "轮机工程",
            "软件工程",
            "轻化工程",
            "边防指挥",
            "边防管理",
            "运动康复",
            "运动训练",
            "迪维希语",
            "通信工程",
            "邮政工程",
            "邮政管理",
            "酒店管理",
            "酿酒工程",
            "采矿工程",
            "采购管理",
            "金融审计",
            "金融工程",
            "金融数学",
            "金融科技",
            "铁路警务",
            "铁道工程",
            "阿拉伯语",
            "音乐教育",
            "音乐治疗",
            "音乐科技",
            "音乐表演",
            "预防医学",
            "风景园林",
            "飞行技术",
            "饲料工程",
            "马业科学",
            "马其顿语",
            "马耳他语",
            "世界史",
            "世界语",
            "中医学",
            "中国画",
            "中药学",
            "丹麦语",
            "书法学",
            "人类学",
            "会计学",
            "传播学",
            "伦理学",
            "侦查学",
            "保险学",
            "傣医学",
            "儿科学",
            "冰岛语",
            "切瓦语",
            "助产学",
            "医工学",
            "印地语",
            "历史学",
            "哈医学",
            "回医学",
            "国际法",
            "地质学",
            "壮医学",
            "外交学",
            "天文学",
            "太极拳",
            "女性学",
            "宗教学",
            "审计学",
            "家政学",
            "工会学",
            "希腊语",
            "广告学",
            "建筑学",
            "德顿语",
            "心理学",
            "戏剧学",
            "投资学",
            "护理学",
            "拉丁语",
            "挪威语",
            "捷克语",
            "政治学",
            "教育学",
            "斐济语",
            "新闻学",
            "朝鲜语",
            "核物理",
            "桑戈语",
            "档案学",
            "毛利语",
            "民族学",
            "汉语言",
            "汤加语",
            "治安学",
            "法医学",
            "波兰语",
            "波斯语",
            "爪哇语",
            "物理学",
            "犯罪学",
            "瑞典语",
            "生态学",
            "电影学",
            "皮金语",
            "监狱学",
            "社会学",
            "祖鲁语",
            "禁毒学",
            "科学史",
            "秘书学",
            "税收学",
            "精算学",
            "纽埃语",
            "绍纳语",
            "经济学",
            "经济林",
            "统计学",
            "维医学",
            "缅甸语",
            "美术学",
            "老年学",
            "老挝语",
            "考古学",
            "自动化",
            "舞蹈学",
            "芬兰语",
            "荷兰语",
            "蒙医学",
            "蒙古语",
            "蒙药学",
            "藏医学",
            "藏药学",
            "警卫学",
            "语言学",
            "豪萨语",
            "财政学",
            "越南语",
            "达里语",
            "逻辑学",
            "金融学",
            "隆迪语",
            "音乐剧",
            "音乐学",
            "马来语",
            "麻醉学",
            "会展",
            "俄语",
            "农学",
            "动画",
            "化学",
            "哲学",
            "园林",
            "园艺",
            "土木",
            "声学",
            "德语",
            "心理",
            "摄影",
            "日语",
            "曲艺",
            "林学",
            "法学",
            "法语",
            "泰语",
            "漫画",
            "烟草",
            "绘画",
            "翻译",
            "英语",
            "茶学",
            "药学",
            "蚕学",
            "蜂学",
            "表演",
            "雕塑"
        ]

        # 1. 标准格式：专业：计算机科学 / 专业:计算机 / 专业 计算机
        match = re.search(r'专业[\s:：]+([一-龥a-zA-Z·]+?)(?:\s|\n|$|，|,|；|;)', text)
        if match:
            result = match.group(1).strip()
            if len(result) >= 2:
                return result

        # 2. 后缀格式：计算机科学专业（要求专业后紧跟分隔符，避免误匹配"通过专业讲解"）
        match = re.search(r'([一-龥a-zA-Z·]{2,})专业(?:\s|，|,|；|;|：|:|\n|$)', text)
        if match:
            result = match.group(1).strip()
            if len(result) >= 2:
                return result

        # 3. 教育背景行格式：xx大学（本科） 国际经济与贸易
        edu_major_match = re.search(r'(?:大学|学院|学校)[（(][^）)]*[）)]\s+([一-龥a-zA-Z·]+)', text)
        if edu_major_match:
            result = edu_major_match.group(1).strip()
            if len(result) >= 2:
                return result

        # 4. 词库回退匹配
        for major in common_majors:
            if major in text:
                return major

        return None

    def _is_zhuanshengben(self, text: str) -> bool:
        """判断本科段是否为专升本（时长 < 3.5 年）

        正常本科 4 年，专升本通常 2 年。
        扫描包含"本科"、"学士"关键词的行，提取起止年份计算时长。
        """
        lines = text.split('\n')
        for line in lines:
            # 只检查包含本科/学士相关关键词的行
            if not any(k in line for k in ('本科', '学士')):
                continue
            # 排除同时含硕士/博士的行（避免误判研究生段）
            if '硕士' in line or '博士' in line or '研究生' in line:
                continue

            # 匹配起止年份：2020.09-2022.06 或 2020.09~2022.06
            m = re.search(r'(\d{4})[\.\-/年]\d{1,2}.*?[-~至—]\s*(\d{4})', line)
            if m:
                start_year = int(m.group(1))
                end_year = int(m.group(2))
                duration = end_year - start_year
                if 0 < duration < 3.5:
                    return True

            # 简化格式：2020-2022（无月份）
            m = re.search(r'(\d{4})\s*[-~至—]\s*(\d{4})', line)
            if m:
                start_year = int(m.group(1))
                end_year = int(m.group(2))
                duration = end_year - start_year
                if 0 < duration < 3.5:
                    return True

        return False

    def _extract_education(self, text: str) -> Optional[str]:
        """提取学历

        规则：
        1. 按学历层级优先级扫描，取最高学历
        2. 本科段若时长 < 3.5 年，判定为专升本
        3. 单独处理"专升本"、"大学专科"、"大学本科"等精确表述
        """
        # 优先级分组：数值越大优先级越高
        priority_groups = [
            # 优先级 5：博士
            (5, {"博士研究生": "博士", "博士": "博士"}),
            # 优先级 4：硕士
            (4, {"硕士研究生": "硕士", "在职研究生": "硕士", "工程硕士": "硕士",
                 "EMBA": "硕士", "MBA": "硕士", "硕士": "硕士", "研究生": "硕士"}),
            # 优先级 3：本科（含专升本）
            (3, {"专升本": "专升本（全日制）", "大学本科": "本科（全日制）",
                 "本科": "本科（全日制）", "学士": "本科（全日制）"}),
            # 优先级 2：专科
            (2, {"大学专科": "专科（全日制）", "高职高专": "专科（全日制）",
                 "大专": "专科（全日制）", "高职": "专科（全日制）", "高专": "专科（全日制）"}),
            # 优先级 1：高中/中专
            (1, {"高中": "高中", "中专": "中专", "职高": "中专", "技校": "中专"}),
            # 优先级 0：初中
            (0, {"初中": "初中"}),
        ]

        highest_priority = -1
        result = None

        for priority, keywords in priority_groups:
            if priority < highest_priority:
                continue
            for key, value in keywords.items():
                if key in text:
                    highest_priority = priority
                    # 本科层级（非明确"专升本"关键词）需要检查时长
                    if priority == 3 and key != "专升本":
                        if self._is_zhuanshengben(text):
                            result = "专升本（全日制）"
                        else:
                            result = value
                    else:
                        result = value

        return result

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
