"""
数据库模块 —— 整个应用的"记账本"
===============================
功能：存、取、改、删候选人的信息

原理很简单：
- SQLite 是一个不需要安装服务器的轻量级数据库，数据存在一个 .db 文件里
- 我们把每个候选人的信息（姓名、电话、学校、评分等）存成一条"记录"
- 需要的时候可以查出来、修改、或者删除
"""

import os
import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import contextmanager


# ========== 安全白名单 ==========
# 这个列表规定了：哪些字段允许被修改。
# 为什么要这样做？防止坏人通过篡改数据来攻击数据库。
# 比如只允许改 "name"、"phone" 这些正常字段，不允许改奇怪的东西。
ALLOWED_UPDATE_FIELDS = {
    "name", "phone", "email", "gender", "birth_year", "school",
    "major", "education", "is_fresh_grad", "channel",
    "communicate_time", "description", "score_total",
    "score_details", "score_source", "ai_score_details", "ai_score_total",
    "result", "resume_raw_text", "phone_transcript",
    "remarks", "intern_name"
}


class Database:
    """
    数据库管理类

    用法示例：
        db = Database()  # 自动创建数据库文件和表
        db.insert_candidate({...})  # 插入一条记录
        candidate = db.get_candidate(1)  # 查询编号为1的候选人
    """

    def __init__(self, db_path: str = "data/recruitment.db"):
        """
        初始化数据库

        参数:
            db_path: 数据库文件存放的位置，默认是 data/recruitment.db
        """
        self.db_path = db_path

        # 如果 data/ 文件夹不存在，自动创建它
        # os.path.dirname("data/recruitment.db") 会拿到 "data"
        folder = os.path.dirname(self.db_path)
        if folder and not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)

        # 创建数据表（如果还没有的话）
        self._init_db()
        # 迁移：为已存在的表添加新列
        self._migrate_db()

    @contextmanager
    def get_connection(self):
        """
        获取数据库连接（用上下文管理器，确保用完自动关闭）

        你可以把它理解为一个"自动关门"的钥匙：
        - with 块开始时开门
        - with 块结束时自动关门，不用担心忘记关
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row  # 让查询结果可以用列名来取值
        # WAL 模式提升读写并发能力，减少 database is locked 概率
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn  # 把连接交给调用方使用
        finally:
            conn.close()  # 用完自动关闭，防止资源泄漏

    def _init_db(self):
        """
        初始化数据表

        创建一张叫 candidates 的表，里面有一列列的字段，
        每个字段对应候选人的一项信息。
        """
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- 自增编号，每条记录唯一
                    name TEXT,                              -- 姓名（允许空，解析失败时用兜底值）
                    phone TEXT,                             -- 手机号
                    email TEXT,                             -- 邮箱
                    gender TEXT,                            -- 性别
                    birth_year INTEGER,                     -- 出生年份（数字）
                    school TEXT,                            -- 学校
                    major TEXT,                             -- 专业
                    education TEXT,                         -- 学历
                    is_fresh_grad TEXT,                     -- 是否应届生（是/否）
                    channel TEXT,                           -- 招聘渠道
                    communicate_time TEXT,                  -- 沟通时间
                    description TEXT,                       -- 台账描述（AI生成的内容）
                    score_total REAL,                       -- 总分（小数）
                    score_details TEXT,                     -- 各维度评分（存成JSON字符串）
                    score_source TEXT DEFAULT 'ai',         -- 评分来源：ai / manual / mixed
                    ai_score_details TEXT,                  -- AI原始各维度评分（JSON）
                    ai_score_total REAL,                    -- AI原始总分
                    result TEXT,                            -- 结果：推荐 / 淘汰 / 空=待审核
                    resume_raw_text TEXT,                   -- 简历原始文本
                    phone_transcript TEXT,                  -- 电话纪要原文
                    remarks TEXT,                           -- 备注
                    intern_name TEXT,                       -- 跟进实习生姓名
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,  -- 创建时间（自动填）
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP   -- 更新时间（自动填）
                )
            """)
            # 评分维度配置表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scoring_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dimension_name TEXT UNIQUE NOT NULL,
                    weight REAL NOT NULL,
                    description TEXT,
                    sort_order INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # API 使用记录表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    feature TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_tokens INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    estimated_cost REAL DEFAULT 0.0
                )
            """)
            conn.commit()  # 保存更改

    def _migrate_db(self):
        """为已存在的表添加新列（兼容旧数据）"""
        with self.get_connection() as conn:
            # 获取当前表的所有列名
            cursor = conn.execute("PRAGMA table_info(candidates)")
            existing_columns = {row[1] for row in cursor.fetchall()}

            # 如果需要，添加 remarks 列
            if "remarks" not in existing_columns:
                conn.execute("ALTER TABLE candidates ADD COLUMN remarks TEXT")
                conn.commit()
            # 如果需要，添加 intern_name 列
            if "intern_name" not in existing_columns:
                conn.execute("ALTER TABLE candidates ADD COLUMN intern_name TEXT")
                conn.commit()
            # 评分系统迭代：添加 score_source, ai_score_details, ai_score_total
            if "score_source" not in existing_columns:
                conn.execute("ALTER TABLE candidates ADD COLUMN score_source TEXT DEFAULT 'ai'")
                conn.commit()
            if "ai_score_details" not in existing_columns:
                conn.execute("ALTER TABLE candidates ADD COLUMN ai_score_details TEXT")
                conn.commit()
            if "ai_score_total" not in existing_columns:
                conn.execute("ALTER TABLE candidates ADD COLUMN ai_score_total REAL")
                conn.commit()

    # ========== 增 ==========

    def insert_candidate(self, data: Dict) -> int:
        """
        插入一条候选人记录

        参数:
            data: 字典，包含候选人的各项信息

        返回:
            新记录的编号（id）
        """
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO candidates (
                    name, phone, email, gender, birth_year, school, major,
                    education, is_fresh_grad, channel, communicate_time,
                    description, score_total, score_details, score_source,
                    ai_score_details, ai_score_total, result,
                    resume_raw_text, phone_transcript, remarks, intern_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("name"),
                data.get("phone"),
                data.get("email"),
                data.get("gender"),
                data.get("birth_year"),
                data.get("school"),
                data.get("major"),
                data.get("education"),
                data.get("is_fresh_grad"),
                data.get("channel"),
                data.get("communicate_time"),
                data.get("description"),
                data.get("score_total"),
                json.dumps(data.get("score_details", {}), ensure_ascii=False),
                data.get("score_source", "ai"),
                json.dumps(data.get("ai_score_details", {}), ensure_ascii=False) if data.get("ai_score_details") else None,
                data.get("ai_score_total"),
                data.get("result"),
                data.get("resume_raw_text"),
                data.get("phone_transcript"),
                data.get("remarks"),
                data.get("intern_name")
            ))
            conn.commit()
            return cursor.lastrowid  # 返回刚插入的这条记录的编号

    # ========== 查 ==========

    def get_candidate(self, candidate_id: int) -> Optional[Dict]:
        """
        根据编号查询单个候选人

        参数:
            candidate_id: 候选人的编号

        返回:
            候选人的信息字典，找不到就返回 None
        """
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM candidates WHERE id = ?", (candidate_id,)
            ).fetchone()
            if row:
                return self._row_to_dict(row)
        return None

    def get_all_candidates(self, result_filter: str = None) -> List[Dict]:
        """
        查询所有候选人（可以按结果筛选）

        参数:
            result_filter: 筛选条件，比如 "推荐"、"淘汰"，不传就查全部

        返回:
            候选人列表，每个候选人是一个字典
        """
        with self.get_connection() as conn:
            if result_filter:
                rows = conn.execute(
                    "SELECT * FROM candidates WHERE result = ? ORDER BY id DESC",
                    (result_filter,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM candidates ORDER BY id DESC"
                ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def search_candidates(self, keyword: str) -> List[Dict]:
        """
        按姓名或手机号搜索候选人

        参数:
            keyword: 搜索关键词

        返回:
            匹配到的候选人列表
        """
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM candidates
                WHERE name LIKE ? OR phone LIKE ?
                ORDER BY id DESC
            """, (f"%{keyword}%", f"%{keyword}%")).fetchall()
            return [self._row_to_dict(row) for row in rows]

    # ========== 改 ==========

    def update_candidate(self, candidate_id: int, data: Dict) -> bool:
        """
        更新候选人信息

        参数:
            candidate_id: 要更新的候选人编号
            data: 要修改的字段和值（字典）

        返回:
            True 表示成功，False 表示没有可更新的内容

        示例：
            db.update_candidate(1, {"result": "推荐"})  # 把1号候选人标记为推荐
        """
        fields = []   # 要更新的字段列表，比如 ["name = ?", "result = ?"]
        values = []   # 对应的值列表

        for key, val in data.items():
            # 安全检查：只允许修改白名单里的字段
            if key not in ALLOWED_UPDATE_FIELDS:
                continue

            fields.append(f"{key} = ?")

            # score_details 是字典，需要先转成 JSON 字符串才能存进数据库
            if key == "score_details":
                values.append(json.dumps(val, ensure_ascii=False))
            else:
                values.append(val)

        # 如果没有要更新的字段，直接返回 False
        if not fields:
            return False

        # 自动更新 updated_at 字段为当前时间
        fields.append("updated_at = ?")
        values.append(datetime.now().isoformat())

        # 最后加上 WHERE 条件（要更新哪一条记录）
        values.append(candidate_id)

        # 拼接 SQL 语句
        # 注意：fields 里的内容是白名单控制的，所以是安全的
        sql = f"UPDATE candidates SET {', '.join(fields)} WHERE id = ?"

        with self.get_connection() as conn:
            conn.execute(sql, values)
            conn.commit()

        return True

    # ========== 评分配置 ==========

    def get_scoring_dimensions(self, active_only: bool = True) -> List[Dict]:
        """
        获取评分维度配置列表

        参数:
            active_only: 是否只返回启用的维度

        返回:
            维度列表，每个维度包含 name, weight, description, sort_order
        """
        with self.get_connection() as conn:
            if active_only:
                rows = conn.execute(
                    "SELECT * FROM scoring_config WHERE is_active = 1 ORDER BY sort_order, id"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM scoring_config ORDER BY sort_order, id"
                ).fetchall()
            return [dict(row) for row in rows]

    def save_scoring_config(self, dimensions: List[Dict]) -> None:
        """
        保存评分维度配置（覆盖式）

        参数:
            dimensions: 维度列表，每项包含 dimension_name, weight, description, sort_order, is_active
        """
        with self.get_connection() as conn:
            # 清空现有配置
            conn.execute("DELETE FROM scoring_config")
            # 插入新配置
            for dim in dimensions:
                conn.execute("""
                    INSERT INTO scoring_config
                    (dimension_name, weight, description, sort_order, is_active)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    dim["dimension_name"],
                    dim["weight"],
                    dim.get("description", ""),
                    dim.get("sort_order", 0),
                    1 if dim.get("is_active", True) else 0
                ))
            conn.commit()

    def get_default_dimensions(self) -> List[Dict]:
        """返回默认的 7 维度评分配置"""
        return [
            {"dimension_name": "动机意愿", "weight": 0.25, "description": "候选人的求职动机和对岗位的意向程度", "sort_order": 0, "is_active": True},
            {"dimension_name": "销售基础能力", "weight": 0.20, "description": "候选人是否具备销售岗位所需的基础能力和经验", "sort_order": 1, "is_active": True},
            {"dimension_name": "沟通逻辑", "weight": 0.15, "description": "候选人的沟通表达能力和逻辑思维", "sort_order": 2, "is_active": True},
            {"dimension_name": "抗压韧性", "weight": 0.15, "description": "候选人在压力下的承受能力和恢复能力", "sort_order": 3, "is_active": True},
            {"dimension_name": "稳定性", "weight": 0.10, "description": "候选人的职业稳定性和留任意愿", "sort_order": 4, "is_active": True},
            {"dimension_name": "自我驱动力", "weight": 0.10, "description": "候选人的主动性和自我激励能力", "sort_order": 5, "is_active": True},
            {"dimension_name": "价值观归因", "weight": 0.05, "description": "候选人的价值观与公司文化的匹配度", "sort_order": 6, "is_active": True},
        ]

    def init_default_scoring_config(self) -> None:
        """如果数据库中没有评分配置，则初始化默认配置"""
        with self.get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM scoring_config").fetchone()[0]
            if count == 0:
                self.save_scoring_config(self.get_default_dimensions())

    # ========== API 用量记录 ==========

    def log_api_usage(self, feature: str, model: str, prompt_tokens: int,
                      completion_tokens: int, estimated_cost: float) -> None:
        """记录一次 API 调用"""
        total = prompt_tokens + completion_tokens
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO api_usage
                (feature, model, prompt_tokens, completion_tokens, total_tokens, estimated_cost)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (feature, model, prompt_tokens, completion_tokens, total, estimated_cost))
            conn.commit()

    def get_api_usage_summary(self, start_date: str, end_date: str) -> List[Dict]:
        """按功能汇总指定日期范围内的 API 用量"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    feature,
                    COUNT(*) as call_count,
                    SUM(prompt_tokens) as prompt_tokens,
                    SUM(completion_tokens) as completion_tokens,
                    SUM(total_tokens) as total_tokens,
                    SUM(estimated_cost) as total_cost
                FROM api_usage
                WHERE date(timestamp) BETWEEN ? AND ?
                GROUP BY feature
                ORDER BY total_cost DESC
            """, (start_date, end_date)).fetchall()
            return [dict(row) for row in rows]

    def get_api_usage_details(self, start_date: str, end_date: str) -> List[Dict]:
        """查询指定日期范围内的 API 调用明细"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    timestamp,
                    feature,
                    model,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    estimated_cost
                FROM api_usage
                WHERE date(timestamp) BETWEEN ? AND ?
                ORDER BY timestamp DESC
            """, (start_date, end_date)).fetchall()
            return [dict(row) for row in rows]

    # ========== 删 ==========

    def delete_candidate(self, candidate_id: int) -> bool:
        """
        删除候选人记录

        参数:
            candidate_id: 要删除的候选人编号

        返回:
            True 表示成功
        """
        with self.get_connection() as conn:
            conn.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))
            conn.commit()
        return True

    # ========== 辅助方法 ==========

    def _row_to_dict(self, row: sqlite3.Row) -> Dict:
        """
        把数据库查询结果（一行）转换成 Python 字典

        这样做的好处是：可以用 candidate["name"] 来取值，
        而不用记 candidate[0] 是姓名、candidate[1] 是电话...
        """
        data = dict(row)

        # score_details 存的是 JSON 字符串，读取时要转回字典
        if data.get("score_details"):
            try:
                data["score_details"] = json.loads(data["score_details"])
            except json.JSONDecodeError:
                data["score_details"] = {}  # 如果解析失败，就当成空字典

        # AI 原始评分也做同样的解析
        if data.get("ai_score_details"):
            try:
                data["ai_score_details"] = json.loads(data["ai_score_details"])
            except json.JSONDecodeError:
                data["ai_score_details"] = {}

        return data
