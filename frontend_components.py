"""
Streamlit Custom Component 封装
================================
将 React 前端组件桥接到 Python Streamlit 应用。

组件构建输出位于 frontend/dist/ 目录，需要在部署前执行:
    cd frontend && npm install && npm run build
"""

import os
import base64
from typing import List, Dict, Any, Optional

import streamlit as st
import streamlit.components.v1 as components

# 组件路径（构建输出目录）
_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")

# 延迟注册：在函数调用时才声明组件，确保 ScriptRunContext 已存在
_zhaopin_component = None


def _get_component():
    """获取或注册组件实例"""
    global _zhaopin_component
    if _zhaopin_component is None:
        _zhaopin_component = components.declare_component(
            "zhaopinhelper",
            path=_FRONTEND_DIR,
        )
    return _zhaopin_component


def _serialize_candidate(c: Dict[str, Any]) -> Dict[str, Any]:
    """将数据库候选人对象序列化为 JSON 安全格式"""
    result = {
        "id": c.get("id"),
        "name": c.get("name") or "",
        "phone": c.get("phone") or "",
        "email": c.get("email") or "",
        "gender": c.get("gender") or "",
        "birth_year": c.get("birth_year"),
        "school": c.get("school") or "",
        "major": c.get("major") or "",
        "education": c.get("education") or "",
        "is_fresh_grad": c.get("is_fresh_grad") or "",
        "channel": c.get("channel") or "",
        "intern_name": c.get("intern_name") or "",
        "communicate_time": c.get("communicate_time") or "",
        "description": c.get("description") or "",
        "remarks": c.get("remarks") or "",
        "result": c.get("result"),
        "score_total": c.get("score_total"),
        "score_details": c.get("score_details") or {},
        "ai_score_details": c.get("ai_score_details") or {},
        "score_source": c.get("score_source") or "",
    }
    return result


def candidate_browser_component(
    candidates: List[Dict[str, Any]],
    selected_id: Optional[int] = None,
    theme: str = "neutral",
    key: str = "candidate_browser",
) -> Optional[Dict[str, Any]]:
    """
    候选人浏览器组件。

    返回组件触发的事件，包含 action 字段：
    - select: 用户选中了某个候选人
    - edit: 用户保存了编辑后的候选人信息
    - delete: 用户请求删除候选人
    - reanalyze: 用户请求 AI 重新识别
    - export: 用户请求导出候选人
    - result_change: 用户更改了候选人的结果状态
    """
    comp = _get_component()
    serialized = [_serialize_candidate(c) for c in candidates]
    return comp(
        component="candidate_browser",
        candidates=serialized,
        selected_id=selected_id,
        theme=theme,
        key=key,
    )


def candidate_upload_component(
    theme: str = "neutral",
    is_processing: bool = False,
    key: str = "candidate_upload",
) -> Optional[Dict[str, Any]]:
    """
    候选人上传组件。

    返回组件触发的事件，包含 action 字段：
    - process_candidates: 用户点击了开始处理，包含 files/transcripts/communicate_time/channel/intern_name
    """
    comp = _get_component()
    return comp(
        component="candidate_upload",
        theme=theme,
        is_processing=is_processing,
        key=key,
    )


class _ComponentFile:
    """兼容 Streamlit UploadedFile 接口的文件包装类"""
    def __init__(self, content: bytes, name: str):
        self.name = name
        self._content = content

    def getvalue(self) -> bytes:
        return self._content


def decode_component_files(event_data: Dict[str, Any]) -> List[_ComponentFile]:
    """
    解码组件传回的 base64 编码文件。

    返回兼容 UploadedFile 接口的对象列表，可直接传给 process_candidates。
    """
    files = event_data.get("files", [])
    decoded = []
    for f in files:
        name = f.get("name", "unknown.pdf")
        content_b64 = f.get("content_base64", "")
        if not content_b64:
            continue
        try:
            content = base64.b64decode(content_b64)
            decoded.append(_ComponentFile(content, name))
        except Exception:
            st.warning(f"解码文件 {name} 失败，已跳过")
    return decoded
