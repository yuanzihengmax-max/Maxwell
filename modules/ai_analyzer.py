"""
AI分析模块 —— 应用的"大脑"
===========================
功能：调用AI（比如ChatGPT）来分析候选人

具体做什么：
1. 读电话纪要 + 简历 → 生成5个维度的台账描述
2. 根据沟通内容 → 给7个维度打分（1-5分）
3. 计算加权总分
4. 从简历里提取可能漏掉的信息（比如姓名、电话没识别到的，让AI再试一次）

原理：
- 我们把简历和电话纪要打包成"提示词"（Prompt）发给AI
- AI读完后，按照我们指定的JSON格式返回结果
- 我们解析JSON，拿到评分和台账内容
"""

import json
from typing import Dict

from config import get_ai_config, DESCRIPTION_DIMENSIONS, calculate_cost


class AIAnalyzer:
    """
    AI分析引擎

    用法示例：
        analyzer = AIAnalyzer(scoring_dimensions=[
            {"dimension_name": "动机意愿", "weight": 0.25},
            ...
        ])
        result = analyzer.analyze_phone_record(
            phone_transcript="电话纪要内容...",
            resume_text="简历内容..."
        )
        print(result["description"])  # 台账描述
        print(result["total_score"])  # 总分
    """

    def __init__(self, scoring_dimensions: list = None, db_instance=None):
        """
        初始化AI引擎

        参数:
            scoring_dimensions: 评分维度配置列表，每项包含 dimension_name 和 weight
            db_instance: Database 实例，用于记录 API 用量

        如果API密钥未配置或缺少依赖库，client 设为 None，
        等真正调用分析时再给出具体错误提示。
        """
        cfg = get_ai_config()
        api_key = cfg.get("api_key", "")
        self.client = None
        self.model = cfg.get("model", "gpt-4o-mini")
        self._init_error = None
        self.scoring_dimensions = scoring_dimensions or []
        self.db = db_instance

        # 检查是不是还没填真实的密钥
        if not api_key or api_key == "your-api-key-here":
            self._init_error = "API_KEY_MISSING"
            return

        # 尝试导入 openai 库
        try:
            from openai import OpenAI, APIError, AuthenticationError
        except ImportError:
            self._init_error = "OPENAI_LIB_MISSING"
            return

        self.client = OpenAI(
            api_key=api_key,
            base_url=cfg.get("base_url")
        )

    def analyze_phone_record(self, phone_transcript: str, resume_text: str) -> Dict:
        """
        分析电话纪要，生成台账内容和评分

        参数:
            phone_transcript: 电话面试纪要的文本内容
            resume_text: 简历的原文

        返回:
            {
                "description": "台账描述内容（5个维度）",
                "scores": {"动机意愿": 4.0, "销售基础能力": 3.5, ...},
                "total_score": 3.72
            }
        """
        # 如果AI未配置，返回具体原因
        if self.client is None:
            if self._init_error == "OPENAI_LIB_MISSING":
                raise RuntimeError(
                    "缺少 openai 依赖库。请在终端运行：pip install openai"
                )
            raise RuntimeError(
                "AI分析功能尚未配置。请前往「系统配置」页面填写 API 密钥。"
            )

        # 如果电话纪要是空的，直接返回空结果，不浪费API调用
        if not phone_transcript or not phone_transcript.strip():
            return {
                "description": "",
                "scores": {},
                "total_score": 0.0
            }

        # 构建提示词
        prompt = self._build_analysis_prompt(phone_transcript, resume_text)

        # 调用AI（带错误处理）
        try:
            from openai import APIError, AuthenticationError

            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"}  # 要求AI返回JSON格式
                )
            except APIError as e:
                err_msg = str(e).lower()
                # 如果是因为 response_format 不支持，降级重试
                if any(k in err_msg for k in ("response_format", "json_object", "unsupported")):
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": self._get_system_prompt()},
                            {"role": "user", "content": prompt}
                        ]
                    )
                else:
                    raise
        except AuthenticationError:
            raise RuntimeError("API密钥错误！请检查系统配置中的 API 密钥是否正确。")
        except APIError as e:
            raise RuntimeError(f"AI服务出错了：{e}")
        except Exception as e:
            raise RuntimeError(f"调用AI时发生未知错误：{e}")

        # 记录 API 用量
        if self.db and hasattr(response, "usage") and response.usage:
            try:
                pt = response.usage.prompt_tokens or 0
                ct = response.usage.completion_tokens or 0
                cost = calculate_cost(self.model, pt, ct)
                self.db.log_api_usage(
                    feature="phone_analysis",
                    model=self.model,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    estimated_cost=cost,
                )
            except Exception:
                pass  # 用量记录失败不影响主流程

        # 获取AI返回的内容
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("AI返回了空内容，请重试。")

        # 解析JSON
        try:
            result = self._parse_json(content)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"AI返回的内容不是有效的JSON格式：{e}")

        # 提取评分并计算总分
        scores = result.get("scores", {})
        total_score = self._calculate_total_score(scores)

        return {
            "description": result.get("description", ""),
            "scores": scores,
            "total_score": total_score,
            "ai_score_details": dict(scores),
            "ai_score_total": total_score,
        }

    def _get_system_prompt(self) -> str:
        """
        系统提示词

        这是告诉AI"你是谁、你要做什么、怎么输出"的指令。
        我们把规则写清楚，AI就会按要求工作。
        """
        # 动态生成评分维度列表
        dim_lines = "\n".join(
            f"- {d.get('dimension_name', '')}"
            for d in self.scoring_dimensions
        )
        # 动态生成示例 scores
        example_scores = ",\n        ".join(
            f'"{d.get("dimension_name", "")}": 4.0'
            for d in self.scoring_dimensions
        )

        return f"""你是一位专业的HR招聘分析师，专门负责销售岗位的招聘评估。

你的任务是根据候选人的简历和电话面试纪要，完成以下两项工作：

【任务一：生成台账描述】
按照以下5个维度整理候选人信息：
1. 基本信息
2. 求职动机&意向度
3. 工作经验&职业规划
4. 综合素质
5. 接受度

每个维度用简洁的语言总结关键信息。

【任务二：评分】
按照以下维度对候选人进行评分（1-5分，保留一位小数）：
{dim_lines}

【输出格式】
必须严格按照以下JSON格式输出，不要添加任何其他文字：
{{
    "description": "1、基本信息：...\\n2、求职动机&意向度：...\\n3、工作经验&职业规划：...\\n4、综合素质：...\\n5、接受度：...",
    "scores": {{
        {example_scores}
    }}
}}"""

    def _build_analysis_prompt(self, phone_transcript: str, resume_text: str) -> str:
        """
        构建分析提示词

        把简历和电话纪要打包，加上评分规则，发给AI。
        如果没有电话纪要，只基于简历进行分析评分。
        """
        dimensions_desc = "\n".join([f"- {d}" for d in DESCRIPTION_DIMENSIONS])
        # 动态生成评分维度及权重说明
        dimensions_score = "\n".join(
            f"- {d.get('dimension_name', '')}（权重{d.get('weight', 0)*100:.0f}%）"
            for d in self.scoring_dimensions
        )

        has_transcript = phone_transcript and phone_transcript.strip()
        transcript_section = f"""【电话面试纪要】
{phone_transcript}""" if has_transcript else """【电话面试纪要】
（无电话面试纪要，请仅基于简历信息进行分析）"""

        return f"""请分析以下候选人信息：

【简历信息】
{resume_text}

{transcript_section}

【任务一：生成台账描述】
按以下5个维度整理信息：
{dimensions_desc}

【任务二：评分】
按以下维度评分（1-5分，保留一位小数）：
{dimensions_score}

{'如果有电话纪要，请结合简历和电话纪要综合评估；' if has_transcript else '由于无电话面试纪要，请仅基于简历内容进行合理推断评分。'}
请严格按照JSON格式输出。"""

    def _calculate_total_score(self, scores: Dict[str, float]) -> float:
        """
        计算加权总分

        使用当前配置的评分维度权重进行计算。
        """
        total = 0.0
        for d in self.scoring_dimensions:
            dim_name = d.get("dimension_name", "")
            weight = d.get("weight", 0)
            score = scores.get(dim_name, 0)
            total += score * weight
        return round(total, 2)

    @staticmethod
    def _parse_json(text: str) -> Dict:
        """
        解析AI返回的JSON内容。

        兼容以下情况：
        1. 纯JSON字符串
        2. 被 markdown 代码块包裹的 JSON（如 ```json {...} ```）
        """
        text = text.strip()
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 尝试提取 markdown 代码块中的 JSON
        if text.startswith("```"):
            # 去掉开头的 ```json 或 ```
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
            return json.loads(text)
        # 尝试从文本中找第一个 { 和最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise json.JSONDecodeError("无法解析JSON", text, 0)

    def extract_missing_info(self, resume_text: str) -> Dict:
        """
        让AI从简历中提取可能漏掉的信息

        比如 PDF解析模块没识别到姓名、出生年份，
        可以让AI再读一遍简历，用"理解"的方式找出来。

        返回：
            {
                "name": "姓名",
                "phone": "手机号",
                "email": "邮箱",
                ...
            }
            如果某项找不到，值就是 null
        """
        current_year = datetime.now().year
        prompt = f"""你是一位专业的简历信息提取助手。请严格遵循以下规则从简历中提取信息。

【字段提取规则】

1. 姓名(name)：
   - 优先查找"姓名"或"Name"标签后面的内容
   - 如果没有标签，找与手机号、邮箱出现在同一区域的2-4个中文字符
   - 必须是真实人名，常见姓氏开头（如张、王、李、刘、陈、杨、赵、黄、周、吴等）
   - ⚠️ 禁止提取职位名称（如"销售经理"、"项目主管"、"工程师"）作为姓名
   - ⚠️ 禁止提取公司名称、品牌名称、项目名称作为姓名
   - ⚠️ 禁止提取"简历"、"求职"、"应聘"、"个人信息"等通用词汇
   - ⚠️ 禁止提取"先生"、"小姐"、"女士"等称谓作为姓名

2. 手机号(phone)：
   - 11位数字，1开头，第二位是3-9
   - 可能包含空格、横杠、括号，请清洗后返回纯数字（如 138-1234-5678 → 13812345678）
   - 不要提取固话号码（如 010-12345678）

3. 邮箱(email)：
   - 标准邮箱格式 xxx@yyy.com
   - 可能因PDF换行被断开（如 xxx@\nqq.com），请合并后返回完整邮箱
   - 常见域名：qq.com、163.com、126.com、gmail.com、outlook.com、sina.com、foxmail.com

4. 性别(gender)：
   - 返回"男"或"女"
   - 可从"性别"标签、身份证号第17位（奇数男偶数女）、或"男/女"字样推断

5. 出生年份(birth_year)：
   - 优先从18位身份证号提取：第7-10位是出生年份（如 11010119950515xxxx → 1995）
   - 可从"出生年月"、"出生日期"、"生日"等字段提取，只返回4位年份数字
   - 合理范围：1960-2015，超出此范围视为无效
   - 如果只有年龄（如"25岁"），用当前年份{current_year}减去年龄推算

6. 学校(school)：
   - 提取最高学历对应的学校名称
   - 包含"大学"、"学院"、"研究院"、"研究所"等后缀的通常是学校
   - 不要提取"XX公司"、"XX集团"作为学校

7. 专业(major)：
   - 提取最高学历对应的专业名称
   - ⚠️ 不要把学位名称当作专业（如"工商管理硕士"是学位，不是专业）
   - 正确示例：计算机科学与技术、市场营销、金融学、机械工程

8. 学历(education) - 必须严格按以下规范返回：
   - 博士研究生 → 博士
   - 硕士研究生/在职研究生/MBA/EMBA/工程硕士 → 硕士
   - 大学本科/本科/学士 → 本科（全日制）
   - 专升本 → 专升本（全日制）
   - 大学专科/大专/高职高专/高职/高专 → 专科（全日制）
   - 高中 → 高中
   - 中专/职高 → 中专
   - 如果看到"研究生在读"、"硕士在读"、"预计202X年硕士毕业" → 硕士
   - 如果看到"本科在读"、"预计202X年本科毕业" → 本科（全日制）
   - 如果看到"专升本在读"、"预计202X年专升本毕业" → 专升本（全日制）

9. 是否应届生(is_fresh_grad)：
   - 简历中明确标注"应届生"、"{current_year}届毕业生"、"应届毕业生" → 是
   - 预计毕业年份为{current_year}年 → 是
   - 已经工作多年或有多年工作经验 → 否
   - 否则返回"否"

【重要约束】
- 如果某项信息在简历中确实找不到，返回 null，不要猜测
- 姓名、手机号、邮箱必须100%确认才能返回，不确定则返回null
- 返回的JSON必须严格符合指定格式，不要添加任何其他字段或说明文字

简历内容：
{resume_text}

请返回以下JSON格式（不要添加markdown代码块标记）：
{{
    "name": "姓名或null",
    "phone": "手机号或null",
    "email": "邮箱或null",
    "gender": "男/女或null",
    "birth_year": 出生年份数字或null,
    "school": "学校名称或null",
    "major": "专业或null",
    "education": "学历或null",
    "is_fresh_grad": "是/否或null"
}}"""

        try:
            from openai import APIError, AuthenticationError

            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"}
                )
            except APIError as e:
                err_msg = str(e).lower()
                if any(k in err_msg for k in ("response_format", "json_object", "unsupported")):
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "user", "content": prompt}
                        ]
                    )
                else:
                    raise
        except AuthenticationError:
            raise RuntimeError("API密钥错误！请检查系统配置中的 API 密钥是否正确。")
        except APIError as e:
            raise RuntimeError(f"AI服务出错了：{e}")
        except Exception as e:
            raise RuntimeError(f"调用AI时发生未知错误：{e}")

        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("AI返回了空内容，请重试。")

        try:
            return self._parse_json(content)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"AI返回的内容不是有效的JSON格式：{e}")
