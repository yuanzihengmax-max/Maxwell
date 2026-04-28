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
    "model": "gpt-4o-mini",
    "api_key": "your-api-key-here",
    "base_url": None
}

# 用户配置文件路径（项目目录下）
USER_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "ai_config.json")


def load_user_config() -> dict:
    """从文件加载用户保存的配置"""
    if not os.path.exists(USER_CONFIG_PATH):
        return {}
    try:
        with open(USER_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 只保留有效的配置项
            return {
                k: v for k, v in data.items()
                if k in ("provider", "model", "api_key", "base_url")
            }
    except (json.JSONDecodeError, IOError):
        return {}


def save_user_config(config: dict) -> None:
    """将用户配置持久化到文件"""
    data = {
        k: v for k, v in config.items()
        if k in ("provider", "model", "api_key", "base_url")
    }
    with open(USER_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clear_user_config() -> None:
    """清除持久化的用户配置"""
    if os.path.exists(USER_CONFIG_PATH):
        os.remove(USER_CONFIG_PATH)


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
        return session_config

    # 2. 线上部署：从 Streamlit Secrets 读取
    secrets_cfg = _load_secrets_config()
    if secrets_cfg.get("api_key") and secrets_cfg["api_key"] != "your-api-key-here":
        st.session_state["ai_config"] = secrets_cfg
        return secrets_cfg

    # 3. 回退到用户配置文件（本地桌面版使用）
    user_cfg = load_user_config()
    if user_cfg.get("api_key") and user_cfg["api_key"] != "your-api-key-here":
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
