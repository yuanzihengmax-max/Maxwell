"""
配置文件
=======
这里放整个应用会用到的固定设置，比如：
- 评分规则的权重
- 招聘渠道列表
- AI接口的配置

用户填写的API配置会持久化到 ai_config.json，刷新浏览器不会丢失。
"""

import json
import os
import re

import streamlit as st

# ========== 评分维度与权重 ==========
# 每个维度占多少比例，加起来应该等于1.0
SCORING_DIMENSIONS = {
    "动机意愿": 0.25,
    "销售基础能力": 0.20,
    "沟通逻辑": 0.15,
    "抗压韧性": 0.15,
    "稳定性": 0.10,
    "自我驱动力": 0.10,
    "价值观归因": 0.05
}

# ========== 台账描述的5个维度 ==========
DESCRIPTION_DIMENSIONS = [
    "基本信息",
    "求职动机&意向度",
    "工作经验&职业规划",
    "综合素质",
    "接受度"
]

# ========== 招聘渠道选项 ==========
CHANNELS = [
    "BOSS直聘",
    "智联招聘",
    "前程无忧",
    "猎聘",
    "新媒体（小红书、抖音等）",
    "内推",
    "校招线下双选会",
    "实习僧",
    "其他"
]

# ========== 学历选项 ==========
EDUCATION_LEVELS = [
    "本科（全日制）",
    "专转本（非全日制）",
    "专转本（全日制）",
    "硕士",
    "专科（全日制）",
    "专科（非全日制）"
]

# ========== AI配置 ==========
AI_CONFIG = {
    "provider": "openai",
    "model": "Qwen/Qwen3-VL-8B-Instruct",
    "api_key": "sk-ltumqpkjpyrebbqwzajpwyqamwwvgjtlwpmuihxfuoavqacr",
    "base_url": "https://api.siliconflow.cn/v1"
}

def _get_user_config_path() -> str:
    """获取当前用户的配置文件路径，支持多用户隔离"""
    base = os.path.dirname(__file__)
    try:
        import streamlit as st
        user_id = st.session_state.get("user_id", "").strip()
        if user_id:
            # 对用户标识做简单清理，避免路径问题
            safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', user_id)
            return os.path.join(base, f"ai_config_{safe_id}.json")
    except Exception:
        pass
    return os.path.join(base, "ai_config.json")


def load_user_config() -> dict:
    """从文件加载用户保存的配置"""
    path = _get_user_config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 只保留有效的配置项
            return {
                k: v for k, v in data.items()
                if k in ("provider", "model", "api_key", "base_url", "resume_extract_prompt")
            }
    except (json.JSONDecodeError, IOError):
        return {}


def _normalize_model_name(model: str, base_url: str) -> str:
    """自动修正常见的模型名称错误，例如 SiliconFlow 缺少 Qwen/ 前缀"""
    if not model or not base_url:
        return model
    # 仅对 SiliconFlow 做 Qwen 系列模型前缀补全
    if "siliconflow" in base_url.lower():
        # Qwen3-VL / Qwen2.5-VL / Qwen-VL 系列没有 Qwen/ 前缀时自动补全
        if model.startswith("Qwen") and not model.startswith("Qwen/"):
            return "Qwen/" + model
    return model


def save_user_config(config: dict) -> None:
    """将用户配置持久化到文件"""
    path = _get_user_config_path()
    data = {
        k: v for k, v in config.items()
        if k in ("provider", "model", "api_key", "base_url", "resume_extract_prompt")
    }
    # 自动修正模型名
    data["model"] = _normalize_model_name(data.get("model", ""), data.get("base_url", ""))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clear_user_config() -> None:
    """清除持久化的用户配置"""
    path = _get_user_config_path()
    if os.path.exists(path):
        os.remove(path)


def _load_secrets_config() -> dict:
    """从 Streamlit Secrets 读取 AI 配置（线上部署时使用）"""
    try:
        # 支持 [siliconflow] 分组或顶层 key
        if "siliconflow" in st.secrets:
            sec = st.secrets["siliconflow"]
            return {
                "provider": sec.get("provider", "openai"),
                "api_key": sec.get("api_key", ""),
                "model": sec.get("model", "gpt-4o-mini"),
                "base_url": sec.get("base_url") or sec.get("baseurl"),
            }
        # 也支持直接写顶层 key
        if "api_key" in st.secrets:
            return {
                "provider": st.secrets.get("provider", "openai"),
                "api_key": st.secrets.get("api_key", ""),
                "model": st.secrets.get("model", "gpt-4o-mini"),
                "base_url": st.secrets.get("base_url") or st.secrets.get("baseurl"),
            }
    except Exception:
        pass
    return {}


def get_ai_config() -> dict:
    """
    获取AI配置。
    优先级：session_state > Streamlit Secrets > 用户配置文件 > 代码默认值
    """
    # 1. 优先取当前会话中的实时配置
    session_config = st.session_state.get("ai_config", {})
    if session_config.get("api_key") and session_config["api_key"] != "your-api-key-here":
        # 实时修正模型名（如缺少 Qwen/ 前缀）
        session_config["model"] = _normalize_model_name(
            session_config.get("model", ""), session_config.get("base_url", "")
        )
        return session_config

    # 2. 线上部署：从 Streamlit Secrets 读取
    secrets_cfg = _load_secrets_config()
    if secrets_cfg.get("api_key") and secrets_cfg["api_key"] != "your-api-key-here":
        secrets_cfg["model"] = _normalize_model_name(secrets_cfg.get("model", ""), secrets_cfg.get("base_url", ""))
        st.session_state["ai_config"] = secrets_cfg
        return secrets_cfg

    # 3. 回退到用户配置文件（本地桌面版使用）
    user_cfg = load_user_config()
    if user_cfg.get("api_key") and user_cfg["api_key"] != "your-api-key-here":
        user_cfg["model"] = _normalize_model_name(user_cfg.get("model", ""), user_cfg.get("base_url", ""))
        st.session_state["ai_config"] = user_cfg
        return user_cfg

    # 4. 最终回退到代码默认值
    return AI_CONFIG


def validate_ai_config() -> list[str]:
    """校验AI配置是否完整，返回缺失的配置项列表"""
    cfg = get_ai_config()
    missing = []
    if not cfg.get("api_key") or cfg.get("api_key") == "your-api-key-here":
        missing.append("AI_API_KEY")
    return missing


# ========== 评分维度动态读取 ==========

def load_scoring_dimensions(db_instance=None) -> list[dict]:
    """
    获取当前评分维度配置。
    优先从数据库读取，如果数据库为空或无法读取则返回代码默认值。

    参数:
        db_instance: Database 实例（从 app.py 传入，避免循环导入）

    返回:
        维度列表，每项为 {"dimension_name": str, "weight": float, ...}
    """
    if db_instance is not None:
        try:
            dims = db_instance.get_scoring_dimensions(active_only=True)
            if dims:
                return dims
        except Exception:
            pass
    # 回退到代码默认值
    return [
        {"dimension_name": k, "weight": v}
        for k, v in SCORING_DIMENSIONS.items()
    ]


def validate_scoring_weights(dimensions: list[dict]) -> tuple[bool, str]:
    """
    校验评分权重配置是否合法。

    参数:
        dimensions: 维度列表

    返回:
        (是否合法, 错误信息)
    """
    if not dimensions:
        return False, "至少需要配置一个评分维度"

    total = sum(d.get("weight", 0) for d in dimensions)
    if abs(total - 1.0) > 0.001:
        return False, f"权重之和必须等于 1.0，当前为 {total:.3f}"

    names = [d.get("dimension_name", "").strip() for d in dimensions]
    if any(not n for n in names):
        return False, "维度名称不能为空"
    if len(names) != len(set(names)):
        return False, "维度名称不能重复"

    for d in dimensions:
        w = d.get("weight", 0)
        if w < 0 or w > 1:
            return False, f"维度 '{d.get('dimension_name')}' 的权重必须在 0~1 之间"

    return True, ""


# ========== 模型单价配置 ==========

def _get_pricing_config_path() -> str:
    """获取模型单价配置文件路径，支持多用户隔离"""
    base = os.path.dirname(__file__)
    try:
        import streamlit as st
        user_id = st.session_state.get("user_id", "").strip()
        if user_id:
            safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', user_id)
            return os.path.join(base, f"model_pricing_{safe_id}.json")
    except Exception:
        pass
    return os.path.join(base, "model_pricing.json")


def load_pricing_config() -> dict:
    """加载用户保存的模型单价配置"""
    path = _get_pricing_config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_pricing_config(pricing_dict: dict) -> None:
    """保存模型单价配置到文件"""
    path = _get_pricing_config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pricing_dict, f, ensure_ascii=False, indent=2)


def get_model_pricing(model_name: str) -> dict:
    """
    获取指定模型的单价配置

    返回:
        {"input": float, "output": float} 或 {}
    """
    cfg = load_pricing_config()
    return cfg.get(model_name, {})


def calculate_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    计算 API 调用费用（人民币）

    参数:
        model_name: 模型名称
        prompt_tokens: 输入 token 数
        completion_tokens: 输出 token 数

    返回:
        估算费用（元），未配置价格的模型返回 0.0
    """
    pricing = get_model_pricing(model_name)
    if not pricing:
        return 0.0
    input_price = pricing.get("input", 0)  # 元 / 百万 tokens
    output_price = pricing.get("output", 0)
    cost = (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000
    return round(cost, 6)
