"""
招聘助手 —— Streamlit 主界面
=============================
这是整个应用的"门面"，把所有模块串在一起，做成一个漂亮的网页。

设计美学：
- 方向：Moss Garden（苔藓庭院）
- 颜色：雨后苔藓底 + 陈年宣纸卡片 + 赭石色强调
- 布局：编辑风格，药丸标签，纸质卡片
- 风格：静谧、有生命力、经得起细品
"""

import os
import tempfile
from datetime import datetime
from typing import List, Dict

import re
import shutil
import sqlite3
import uuid
import streamlit as st

from config import CHANNELS, SCORING_DIMENSIONS, AI_CONFIG, validate_ai_config, get_ai_config, save_user_config, clear_user_config, load_scoring_dimensions, validate_scoring_weights, load_pricing_config, save_pricing_config, calculate_cost
from modules.pdf_parser import PDFParser
from modules.ai_analyzer import AIAnalyzer
from modules.database import Database
from modules.excel_exporter import ExcelExporter


# ========== 自定义 CSS 样式 ==========
# 通过注入 CSS，把 Streamlit 默认的朴素样式改成我们想要的精致风格
CUSTOM_CSS = """
<style>
/* ===== 1. Font Imports ===== */
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700&family=Noto+Sans+SC:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ===== 2. CSS Variables ===== */
:root {
    --bg-primary: #15251A;
    --bg-card: #F5F0E8;
    --bg-elevated: #EDE8DE;
    --bg-dark: #0F1E15;
    --text-primary: #1A2E22;
    --text-secondary: #5A7A65;
    --text-muted: #6B8A72;
    --text-inverse: #F5F0E8;
    --accent: #B87A4A;
    --accent-hover: #A0683E;
    --accent-light: #F0E6D8;
    --accent-glow: rgba(184, 122, 74, 0.15);
    --success: #4A7C59;
    --success-light: #E4EDE6;
    --danger: #A84A4A;
    --danger-light: #F2E4E4;
    --warning: #B8922A;
    --warning-light: #F2EBD4;
    --info: #4A7A8A;
    --info-light: #E4ECEF;
    --border-light: #DDD8CE;
    --border-medium: #B8B2A6;
    --shadow-sm: 0 1px 2px rgba(15, 30, 21, 0.06);
    --shadow-md: 0 4px 12px rgba(15, 30, 21, 0.08);
    --shadow-lg: 0 12px 32px rgba(15, 30, 21, 0.10);
}

/* ===== 3. Global Base ===== */
.stApp {
    background-color: var(--bg-primary) !important;
    font-family: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    color: var(--text-inverse);
}

/* Paper grain texture overlay */
.stApp::before {
    content: "";
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
    opacity: 0.03;
    pointer-events: none;
    z-index: 9999;
}

/* Hide default Streamlit header */
header[data-testid="stHeader"] {
    display: none !important;
}

/* Fix: Streamlit dataframe (glide-data-grid) uses icon ligatures in its context menu.
   Our CJK font breaks these ligatures, causing text overlap.
   Force system font stack inside the dataframe. */
.gdg-style, .gdg-style *, [class*="gdg-"], [class*="gdg-"] *,
[data-testid="stDataFrame"], [data-testid="stDataFrame"] *,
[data-testid="stDataFrameResizable"] *, [data-testid="data-grid-canvas"] * {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji' !important;
}

/* Main content width */
.block-container {
    max-width: 1100px;
    padding-top: 2rem;
    padding-bottom: 4rem;
}

/* ===== 4. Typography ===== */
/* Default: light text for dark page background */
h1, h2, h3, h4 {
    font-family: 'Noto Serif SC', 'Songti SC', 'STSong', serif !important;
    color: var(--text-inverse) !important;
    font-weight: 700 !important;
    letter-spacing: 0.02em !important;
}

/* Inside light cards: dark text */
[data-testid="stVerticalBlockBorderWrapper"] h1,
[data-testid="stVerticalBlockBorderWrapper"] h2,
[data-testid="stVerticalBlockBorderWrapper"] h3,
[data-testid="stVerticalBlockBorderWrapper"] h4,
.stFileUploader h1, .stFileUploader h2, .stFileUploader h3, .stFileUploader h4 {
    color: var(--text-primary) !important;
}

h1 {
    font-size: 2.8rem !important;
    line-height: 1.2 !important;
    margin-bottom: 0.5rem !important;
}

h2 {
    font-size: 1.6rem !important;
    font-weight: 600 !important;
    margin-top: 2rem !important;
    margin-bottom: 1rem !important;
}

h3 {
    font-size: 1.2rem !important;
    font-weight: 600 !important;
    margin-top: 1.5rem !important;
}

h4 {
    font-family: 'Noto Serif SC', 'Songti SC', 'STSong', serif !important;
    color: var(--text-inverse) !important;
    font-size: 1.05rem !important;
    font-weight: 600 !important;
    margin-top: 1.2rem !important;
    margin-bottom: 0.75rem !important;
    letter-spacing: 0.01em !important;
}

/* Safe font override: only target visible user content.
   NEVER use !important on bare tags (p, div, span…) — that breaks
   Streamlit internal icon fonts (glide-data-grid, expander icons). */
.stMarkdown, .stMarkdown p, .stMarkdown span, .stMarkdown li,
.stCaption, .stCaption span,
.stWrite, .stWrite p, .stWrite span,
.stAlert, .stAlert p, .stAlert span, .stAlert strong,
[data-testid="stMetric"] > div {
    font-family: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    line-height: 1.6;
}

/* Title rule — gold accent line */
.title-rule {
    width: 48px;
    height: 3px;
    background-color: var(--accent);
    margin: 0.75rem 0 1.5rem 0;
}

.subtitle {
    font-family: 'Noto Sans SC', 'PingFang SC', sans-serif !important;
    color: var(--text-secondary) !important;
    font-size: 0.95rem !important;
    letter-spacing: 0.04em !important;
    margin-top: 1.2rem !important;
}

/* ===== 5. Tab Navigation — Pill Style ===== */
.stTabs [data-baseweb="tab-list"] {
    gap: 12px;
    background: transparent;
    border-bottom: none !important;
    padding-bottom: 8px;
    margin-bottom: 2rem;
}

.stTabs [data-baseweb="tab"] {
    background: transparent;
    border: 1.5px solid rgba(184, 122, 74, 0.3);
    border-radius: 100px;
    color: var(--text-muted);
    font-weight: 500;
    font-size: 0.9rem;
    padding: 8px 24px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    font-family: 'Noto Sans SC', 'PingFang SC', sans-serif !important;
}

.stTabs [data-baseweb="tab"]:hover {
    color: var(--text-inverse);
    border-color: var(--accent);
    background: rgba(184, 122, 74, 0.1);
}

.stTabs [aria-selected="true"] {
    color: var(--text-inverse) !important;
    background: var(--accent) !important;
    border-color: var(--accent) !important;
    box-shadow: 0 2px 12px var(--accent-glow) !important;
}

/* ===== 6. Cards & Containers ===== */
/* Loosened selector: Streamlit nests border wrappers deeper than direct child */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-light) !important;
    border-radius: 2px !important;
    box-shadow: var(--shadow-sm) !important;
    padding: 1.75rem !important;
    margin-bottom: 1.5rem !important;
    transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1),
                box-shadow 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    animation: fadeSlideUp 0.5s ease-out both;
}

div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-md) !important;
}

/* ===== 7. Buttons ===== */
.stButton > button {
    font-family: 'Noto Sans SC', 'PingFang SC', sans-serif !important;
    border-radius: 2px !important;
    padding: 10px 28px !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    letter-spacing: 0.06em !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    border: none !important;
    text-align: center !important;
    justify-content: center !important;
}

/* Primary button */
.stButton > button[kind="primary"] {
    background-color: var(--accent) !important;
    color: var(--bg-primary) !important;
    box-shadow: 0 2px 8px var(--accent-glow) !important;
}

.stButton > button[kind="primary"]:hover {
    background-color: var(--accent-hover) !important;
    box-shadow: 0 4px 16px rgba(184, 122, 74, 0.25) !important;
    transform: translateY(-1px) !important;
}

.stButton > button[kind="primary"]:active {
    transform: translateY(0) !important;
}

/* Secondary button */
.stButton > button[kind="secondary"] {
    background-color: var(--bg-dark) !important;
    color: var(--text-inverse) !important;
    border: 1.5px solid var(--border-medium) !important;
    box-shadow: none !important;
}

.stButton > button[kind="secondary"]:hover {
    background-color: var(--bg-primary) !important;
    border-color: var(--accent) !important;
    color: var(--accent) !important;
}

.stButton > button:disabled {
    background-color: #C8C3B8 !important;
    color: #3A4A3E !important;
    box-shadow: none !important;
    transform: none !important;
    cursor: not-allowed !important;
}

/* ===== 8. Form Inputs ===== */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    background-color: var(--bg-elevated) !important;
    border: 1.5px solid var(--border-light) !important;
    border-radius: 2px !important;
    color: var(--text-primary) !important;
    caret-color: var(--text-primary) !important;
    font-size: 0.95rem !important;
    padding: 12px 16px !important;
    font-family: 'Noto Sans SC', 'PingFang SC', sans-serif !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}

/* Number input */
[data-testid="stNumberInput"] input {
    color: var(--text-primary) !important;
    caret-color: var(--text-primary) !important;
}

/* Selectbox: target the visible value container, not all nested divs */
.stSelectbox > div[data-baseweb="select"] > div {
    background-color: var(--bg-elevated) !important;
    border: 1.5px solid var(--border-light) !important;
    border-radius: 2px !important;
    color: var(--text-primary) !important;
    font-size: 0.95rem !important;
    font-family: 'Noto Sans SC', 'PingFang SC', sans-serif !important;
    min-height: 44px !important;
}

.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px var(--accent-glow) !important;
    background-color: var(--bg-elevated) !important;
}

/* Placeholder color */
.stTextInput input::placeholder,
.stTextArea textarea::placeholder {
    color: var(--text-secondary) !important;
    opacity: 0.8 !important;
}

/* Disabled textarea: ensure dark readable text on light background */
textarea:disabled,
textarea[disabled],
textarea[aria-disabled="true"],
[data-baseweb="textarea"] textarea:disabled,
[data-baseweb="textarea"] textarea[disabled],
[data-testid="stTextArea"] textarea:disabled,
[data-testid="stTextArea"] textarea[disabled],
.stTextArea textarea:disabled,
.stTextArea > div textarea:disabled,
.stTextArea [data-testid="stTextAreaContainer"] textarea:disabled {
    color: #1A2E22 !important;
    opacity: 1 !important;
    -webkit-text-fill-color: #1A2E22 !important;
    background-color: #F5F0E8 !important;
}

.stSelectbox > div[data-baseweb="select"] > div:focus-within {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px var(--accent-glow) !important;
}

/* Selectbox dropdown menu and options */
[data-baseweb="menu"],
[data-baseweb="menu"] > div,
[data-baseweb="menu"] [role="listbox"] {
    background-color: var(--bg-elevated) !important;
    color: #1A2E22 !important;
}

[data-baseweb="menu"] [role="option"],
[data-baseweb="menu"] li {
    color: #1A2E22 !important;
    background-color: var(--bg-elevated) !important;
}

[data-baseweb="menu"] [role="option"]:hover,
[data-baseweb="menu"] [role="option"][aria-selected="true"],
[data-baseweb="menu"] li:hover {
    background-color: var(--accent-light) !important;
    color: #1A2E22 !important;
}

/* Selectbox arrow icon */
.stSelectbox svg[data-testid="stIconChevronDown"] {
    color: #1A2E22 !important;
    fill: #1A2E22 !important;
}

/* ALL interactive icons inside light form inputs — force dark for visibility */
.stTextInput svg, .stTextInput [data-testid] svg,
.stTextArea svg, .stTextArea [data-testid] svg,
.stSelectbox svg, .stSelectbox [data-testid] svg,
.stDateInput svg, .stDateInput [data-testid] svg,
[data-testid="stNumberInput"] svg, [data-testid="stNumberInput"] [data-testid] svg {
    color: #1A2E22 !important;
    fill: #1A2E22 !important;
    stroke: #1A2E22 !important;
}

/* Buttons inside inputs: password toggle, clear button, calendar picker, stepper */
.stTextInput button,
.stTextArea button,
.stSelectbox button,
.stDateInput button,
[data-testid="stNumberInput"] button {
    color: #1A2E22 !important;
}
.stTextInput button svg,
.stTextArea button svg,
.stSelectbox button svg,
.stDateInput button svg,
[data-testid="stNumberInput"] button svg {
    color: #1A2E22 !important;
    fill: #1A2E22 !important;
    stroke: #1A2E22 !important;
}

/* Placeholder text: darker for contrast on light input bg */
.stTextInput input::placeholder,
.stTextArea textarea::placeholder,
.stDateInput input::placeholder,
[data-testid="stNumberInput"] input::placeholder {
    color: #3A5A45 !important;
    opacity: 1 !important;
}

/* Buttons inside light cards: force dark background so they stand out */
[data-testid="stVerticalBlockBorderWrapper"] .stButton > button,
[data-testid="stVerticalBlockBorderWrapper"] .stButton > button[kind="primary"],
[data-testid="stVerticalBlockBorderWrapper"] .stButton > button[kind="secondary"] {
    background-color: #1A2E22 !important;
    color: #F5F0E8 !important;
    border: 1.5px solid #3A4A3E !important;
    box-shadow: none !important;
}
[data-testid="stVerticalBlockBorderWrapper"] .stButton > button:hover,
[data-testid="stVerticalBlockBorderWrapper"] .stButton > button[kind="primary"]:hover,
[data-testid="stVerticalBlockBorderWrapper"] .stButton > button[kind="secondary"]:hover {
    background-color: #0F1E15 !important;
    border-color: #B87A4A !important;
    color: #B87A4A !important;
}
[data-testid="stVerticalBlockBorderWrapper"] .stButton > button:disabled {
    background-color: #C8C3B8 !important;
    color: #3A4A3E !important;
    border-color: #B8B2A6 !important;
}

/* Date input — comprehensive fix for dark-theme text visibility.
   Streamlit 1.50+ uses Base Web MaskedInput for st.date_input.
   The placeholder is rendered as a separate aria-hidden div, NOT as
   a native ::placeholder, so we must target both. */
[data-testid="stDateInput"] input,
.stDateInput input {
    color: #1A2E22 !important;
    -webkit-text-fill-color: #1A2E22 !important;
    caret-color: #1A2E22 !important;
}

/* Base Web MaskedInput placeholder div (aria-hidden, sits before <input>) */
[data-testid="stDateInput"] div[aria-hidden="true"]:has(+ input),
.stDateInput div[aria-hidden="true"]:has(+ input) {
    color: #3A5A45 !important;
}
/* Fallback for browsers without :has() support */
[data-testid="stDateInput"] [aria-hidden="true"],
.stDateInput [aria-hidden="true"] {
    color: #3A5A45 !important;
}

/* Native ::placeholder (kept as a safety net) */
[data-testid="stDateInput"] input::placeholder,
.stDateInput input::placeholder {
    color: #3A5A45 !important;
    opacity: 1 !important;
    -webkit-text-fill-color: #3A5A45 !important;
}

/* Date-input label */
[data-testid="stDateInput"] label,
.stDateInput label {
    color: #1A2E22 !important;
}

/* Calendar picker icon */
[data-testid="stDateInput"] input::-webkit-calendar-picker-indicator,
.stDateInput input::-webkit-calendar-picker-indicator {
    filter: invert(0.3) !important;
    cursor: pointer !important;
}

/* ===== 9. File Uploader ===== */
.stFileUploader > div > div > div {
    background-color: color-mix(in srgb, var(--bg-card) 50%, transparent) !important;
    border: 2px dashed var(--border-medium) !important;
    border-radius: 2px !important;
    color: var(--text-secondary) !important;
    transition: all 0.2s ease !important;
}

.stFileUploader > div > div > div:hover {
    border-color: var(--accent) !important;
    background-color: var(--accent-light) !important;
}

/* ===== 10. Data Tables ===== */
[data-testid="stDataFrame"] {
    border-radius: 2px !important;
    overflow: hidden !important;
    box-shadow: var(--shadow-sm) !important;
    border: 1px solid var(--border-light) !important;
}

[data-testid="stDataFrame"] table {
    font-family: 'Noto Sans SC', 'PingFang SC', sans-serif !important;
    border-collapse: collapse !important;
}

[data-testid="stDataFrame"] th {
    background-color: var(--bg-dark) !important;
    color: var(--text-inverse) !important;
    font-weight: 600 !important;
    padding: 12px 16px !important;
    text-align: left !important;
    font-size: 0.85rem !important;
    letter-spacing: 0.04em !important;
}

[data-testid="stDataFrame"] td {
    padding: 12px 16px !important;
    border-bottom: 1px solid var(--border-light) !important;
    color: var(--text-primary) !important;
}

[data-testid="stDataFrame"] tr:nth-child(even) {
    background-color: var(--bg-card) !important;
}

[data-testid="stDataFrame"] tr:hover {
    background-color: var(--accent-light) !important;
}

/* ===== 11. Alerts & Notifications ===== */
/* Dark subtle cards with top accent line — unified palette, no jarring bright backgrounds */
.stAlert {
    background-color: rgba(26, 46, 34, 0.55) !important;
    border: 1px solid rgba(245, 240, 232, 0.1) !important;
    border-radius: 2px !important;
    padding: 1rem 1.25rem !important;
    font-family: 'Noto Sans SC', 'PingFang SC', sans-serif !important;
}

/* Top accent line distinguishes type without large color blocks */
.stAlert[data-testid="stNotificationContentError"] {
    border-top: 2px solid var(--danger) !important;
    background-color: rgba(168, 74, 74, 0.1) !important;
}
.stAlert[data-testid="stNotificationContentInfo"] {
    border-top: 2px solid var(--accent) !important;
    background-color: rgba(184, 122, 74, 0.1) !important;
}
.stAlert[data-testid="stNotificationContentSuccess"] {
    border-top: 2px solid var(--success) !important;
    background-color: rgba(74, 124, 89, 0.1) !important;
}
.stAlert[data-testid="stNotificationContentWarning"] {
    border-top: 2px solid var(--warning) !important;
    background-color: rgba(184, 146, 42, 0.1) !important;
}

/* All text inside alerts — light for readability on dark card */
.stAlert,
.stAlert p,
.stAlert span,
.stAlert div,
.stAlert strong,
.stAlert label,
.stAlert li,
.stAlert h1,
.stAlert h2,
.stAlert h3,
.stAlert h4 {
    color: var(--text-inverse) !important;
}

.stAlert code {
    background-color: rgba(245, 240, 232, 0.15) !important;
    color: var(--accent-light) !important;
    padding: 2px 6px !important;
    border-radius: 2px !important;
    font-family: 'JetBrains Mono', 'SF Mono', monospace !important;
    font-size: 0.85em !important;
}

/* ===== 12. Metrics ===== */
[data-testid="stMetric"] {
    background: transparent !important;
    border: none !important;
    border-bottom: 2px solid var(--accent) !important;
    border-radius: 0 !important;
    padding: 1rem 0 !important;
}

[data-testid="stMetric"] > div > div:first-child {
    color: var(--text-secondary) !important;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.1em !important;
    font-family: 'Noto Sans SC', 'PingFang SC', sans-serif !important;
}

[data-testid="stMetric"] > div > div:last-child {
    color: var(--text-inverse) !important;
    font-size: 2.2rem !important;
    font-weight: 700 !important;
    font-family: 'Noto Serif SC', 'Songti SC', serif !important;
}

/* ===== 13. Progress Bars ===== */
/* Track background */
[data-testid="stProgress"] > div {
    background-color: rgba(245, 240, 232, 0.12) !important;
    border-radius: 2px !important;
}

/* Actual progress fill */
[data-testid="stProgress"] > div > div {
    background-color: var(--accent) !important;
    border-radius: 2px !important;
}

/* Progress text label above bar */
[data-testid="stProgress"] [class*="st-emotion"] {
    color: var(--text-inverse) !important;
    font-family: 'Noto Sans SC', 'PingFang SC', sans-serif !important;
}

/* ===== 14. Expanders ===== */
.stExpander {
    border: 1px solid var(--border-light) !important;
    border-radius: 2px !important;
    background: var(--bg-card) !important;
    color: var(--text-primary) !important;
    overflow: hidden !important;
    box-shadow: var(--shadow-sm) !important;
}

.stExpander > div:first-child {
    background: var(--bg-primary) !important;
    color: var(--text-inverse) !important;
    font-weight: 600 !important;
    padding: 1rem 1.5rem !important;
    border-bottom: 1px solid var(--border-light) !important;
}

/* Protect expander icon fonts from inherited CJK font */
.stExpander > div:first-child button *,
.stExpander > div:first-child [data-testid="stExpanderToggleIcon"],
.stExpander [role="button"] svg,
.stExpander [role="button"] [data-testid] {
    font-family: revert !important;
}

/* ===== 15. Dividers ===== */
hr {
    border: none !important;
    border-top: 1px solid var(--border-light) !important;
    margin: 2rem 0 !important;
}

.stDivider {
    background-color: var(--border-light) !important;
}

/* ===== 16. Checkbox & Radio ===== */
.stCheckbox > div > div > div,
.stRadio > div > div > div {
    background-color: var(--bg-elevated) !important;
    border: 1.5px solid var(--border-light) !important;
}

.stCheckbox > div > div > div[data-checked="true"],
.stRadio > div > div > div[data-checked="true"] {
    background-color: var(--accent) !important;
    border-color: var(--accent) !important;
}

/* ===== 17. Spinner / Loading ===== */
[data-testid="stSpinner"] > div {
    border-color: var(--accent) !important;
    border-top-color: transparent !important;
}

/* ===== 18. Animations ===== */
@keyframes fadeSlideUp {
    from {
        opacity: 0;
        transform: translateY(20px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@keyframes fadeSlideIn {
    from {
        opacity: 0;
        transform: translateX(-10px);
    }
    to {
        opacity: 1;
        transform: translateX(0);
    }
}

/* Apply entrance animation to main content blocks only */
.block-container > div > div[data-testid="stVerticalBlock"] {
    animation: fadeSlideUp 0.5s ease-out both;
}

/* Stagger cards */
div[data-testid="stVerticalBlockBorderWrapper"]:nth-child(1) { animation-delay: 0.08s; }
div[data-testid="stVerticalBlockBorderWrapper"]:nth-child(2) { animation-delay: 0.16s; }
div[data-testid="stVerticalBlockBorderWrapper"]:nth-child(3) { animation-delay: 0.24s; }
div[data-testid="stVerticalBlockBorderWrapper"]:nth-child(4) { animation-delay: 0.32s; }

/* ===== 19. Custom Utility Classes ===== */
.accent-text { color: var(--accent) !important; }
.muted-text { color: var(--text-muted) !important; }
.secondary-text { color: var(--text-secondary) !important; }

/* Section label */
.section-label {
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.12em !important;
    color: var(--text-secondary) !important;
    margin-bottom: 0.5rem !important;
}

/* Status badges */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 100px;
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.02em;
}

.badge-recommend {
    background-color: var(--success-light);
    color: var(--success);
}

.badge-eliminate {
    background-color: var(--danger-light);
    color: var(--danger);
}

.badge-pending {
    background-color: var(--warning-light);
    color: var(--warning);
}
</style>
"""

# 注入 CSS
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# JS 兜底：强制修复日期选择器文字颜色（Base Web/Styletron 会动态注入原子 CSS，
# 偶尔覆盖我们的规则；这段脚本通过 MutationObserver 在组件挂载后立即修正颜色）
st.markdown("""
<script>
(function() {
    if (window.__dateInputFixApplied) return;
    window.__dateInputFixApplied = true;

    function fixDateInputs() {
        // 1. 修复 input 本体文字
        document.querySelectorAll('[data-testid="stDateInput"] input').forEach(function(el) {
            el.style.setProperty('color', '#1A2E22', 'important');
            el.style.setProperty('-webkit-text-fill-color', '#1A2E22', 'important');
        });
        // 2. 修复 Base Web 的 placeholder div（aria-hidden 的文本节点）
        document.querySelectorAll('[data-testid="stDateInput"] [aria-hidden="true"]').forEach(function(el) {
            if (el.children.length === 0 && el.textContent.trim().length > 0) {
                el.style.setProperty('color', '#3A5A45', 'important');
            }
        });
    }

    fixDateInputs();
    var observer = new MutationObserver(fixDateInputs);
    observer.observe(document.body, { childList: true, subtree: true });
})();
</script>
""", unsafe_allow_html=True)

# ========== 模块初始化 ==========

@st.cache_resource
def init_parser() -> PDFParser:
    return PDFParser()


@st.cache_resource
def init_analyzer(scoring_dimensions: list = None) -> AIAnalyzer:
    return AIAnalyzer(scoring_dimensions=scoring_dimensions)


@st.cache_resource
def init_exporter() -> ExcelExporter:
    return ExcelExporter()


def get_database() -> Database:
    """每个会话独立获取Database实例（支持多用户隔离）"""
    user_id = st.session_state.get("user_id", "").strip()
    if user_id:
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', user_id)
        db_path = f"data/recruitment_{safe_id}.db"
    else:
        db_path = "data/recruitment.db"
    db = Database(db_path=db_path)
    db.init_default_scoring_config()
    return db


def get_modules():
    """获取模块实例"""
    db = get_database()
    scoring_dims = load_scoring_dimensions(db_instance=db)
    return {
        "pdf_parser": init_parser(),
        "ai_analyzer": AIAnalyzer(scoring_dimensions=scoring_dims, db_instance=db),  # 不缓存，确保配置更改后立即生效
        "database": db,
        "excel_exporter": init_exporter(),
        "scoring_dimensions": scoring_dims,
    }


# ========== 主界面 ==========

def main():
    # ===== 用户标识（多用户隔离）=====
    if "user_id" not in st.session_state:
        st.session_state["user_id"] = ""

    if not st.session_state["user_id"]:
        st.markdown(
            "<h1 style='margin-bottom: 0; color: var(--text-inverse) !important;'>"
            "招聘助手"
            "</h1>"
            "<div class='title-rule'></div>",
            unsafe_allow_html=True
        )
        st.markdown(
            "<p class='secondary-text' style='margin-bottom: 1.5rem;'>"
            "请输入您的用户标识，用于隔离您的 AI 配置和历史记录"
            "</p>",
            unsafe_allow_html=True
        )
        col_input, col_btn = st.columns([3, 1])
        with col_input:
            user_input = st.text_input(
                "用户标识",
                key="_user_id_input",
                placeholder="例如：zhangsan",
                label_visibility="collapsed",
            )
        with col_btn:
            if st.button("确认", type="primary", use_container_width=True):
                if user_input and user_input.strip():
                    new_user = user_input.strip()
                    # 彻底清除旧会话状态，防止数据残留
                    for key in list(st.session_state.keys()):
                        if key != "user_id":
                            del st.session_state[key]
                    st.session_state["user_id"] = new_user
                    st.rerun()
        st.stop()
        return

    # 页面标题 — 不对称编辑风格
    header_left, header_right = st.columns([3, 2])
    with header_left:
        st.markdown(
            "<h1 style='margin-bottom: 0; color: var(--text-inverse) !important;'>"
            "招聘助手"
            "</h1>"
            "<div class='title-rule'></div>",
            unsafe_allow_html=True
        )
    with header_right:
        user_id = st.session_state.get("user_id", "")
        # 使用原生 Streamlit 组件展示，避免用户输入直接嵌入 HTML 导致 XSS
        _, right_area = st.columns([1, 2])
        with right_area:
            st.markdown(
                "<p style='text-align: right; margin-top: 0.5rem;'>"
                "销售岗位招聘管理系统 <span style='font-size: 0.7rem; color: #9CA3AF;'>v6.2</span>"
                "</p>",
                unsafe_allow_html=True
            )
            display_user = user_id[:20] + "..." if len(user_id) > 20 else user_id
            st.caption(f"当前用户：{display_user}")

    # 检查AI配置
    missing_config = validate_ai_config()
    if missing_config:
        st.error(f"AI 服务未配置: {', '.join(missing_config)}")
        st.info(
            "请前往「系统配置」页面填写 API 信息，"
            "或提前设置环境变量：`export AI_API_KEY=your-api-key`"
        )

    # 四个主标签页
    tab1, tab2, tab3, tab4 = st.tabs(
        ["新增候选人", "历史记录", "台账导出", "系统配置"]
    )

    with tab1:
        render_add_candidate()

    with tab2:
        render_history()

    with tab3:
        render_export()

    with tab4:
        render_settings()


# ========== 标签页1：新增候选人 ==========

def render_add_candidate():
    """新增候选人页面"""
    # 如果还有待审核的候选人，展示结果
    if st.session_state.get("pending_candidates"):
        show_pending_results()
        return

    st.markdown("### 新增候选人")
    st.markdown(
        "<p class='secondary-text' style='margin-bottom: 1.5rem;'>"
        "上传简历 → 输入电话纪要 → AI自动分析"
        "</p>",
        unsafe_allow_html=True
    )

    # 第一步：上传简历
    with st.container(border=True):
        st.markdown("#### 第一步：上传简历")
        uploaded_files = st.file_uploader(
            "拖拽或点击上传简历PDF文件",
            type="pdf",
            accept_multiple_files=True
        )

    if not uploaded_files:
        st.info("请先上传简历PDF文件，支持同时上传多份")
        return

    # 第二步：输入电话纪要
    with st.container(border=True):
        st.markdown("#### 第二步：输入电话纪要")

        phone_transcripts = {}
        for file in uploaded_files:
            name = file.name.replace(".pdf", "")
            transcript = st.text_area(
                f"候选人：**{name}**",
                height=120,
                key=f"transcript_{name}",
                placeholder="请粘贴该候选人的电话面试纪要内容..."
            )
            phone_transcripts[name] = transcript

    # 第三步：补充信息
    with st.container(border=True):
        st.markdown("#### 第三步：补充信息")

        col1, col2 = st.columns(2)
        with col1:
            communicate_date = st.date_input("沟通日期", datetime.now())
        with col2:
            channel = st.selectbox("招聘渠道", CHANNELS)

        # 实习生姓名：优先用当前登录用户，记住最后一次输入
        default_intern = st.session_state.get("user_id", "")
        if "last_intern_name" not in st.session_state:
            st.session_state["last_intern_name"] = default_intern
        intern_name = st.text_input(
            "跟进实习生",
            value=st.session_state["last_intern_name"],
            placeholder="请输入跟进此候选人的实习生姓名"
        )
        if intern_name != st.session_state.get("last_intern_name", ""):
            st.session_state["last_intern_name"] = intern_name

        communicate_datetime = str(communicate_date)

    # 开始处理按钮
    col_btn, _ = st.columns([1, 3])
    with col_btn:
        if st.button("开始分析处理", type="primary", width="stretch"):
            with st.spinner("正在处理候选人..."):
                try:
                    process_candidates(uploaded_files, phone_transcripts,
                                       communicate_datetime, channel, intern_name)
                except RuntimeError as e:
                    err_msg = str(e)
                    if "API密钥错误" in err_msg or "密钥" in err_msg:
                        st.error("🔑 API 密钥无效，请前往「系统配置」页面检查。")
                    elif "AI服务出错" in err_msg:
                        st.error("🤖 AI 服务暂时不可用，请稍后再试。")
                    elif "AI返回" in err_msg:
                        st.error(f"📝 AI 返回异常：{err_msg}")
                    else:
                        st.error(f"❌ 处理失败：{err_msg}")
                except Exception as e:
                    st.error(f"❌ 处理失败：{e}")


def _extract_name_from_filename(filename: str) -> str:
    """从文件名中提取候选人姓名（兜底用）"""
    # 去掉扩展名
    name = filename.replace(".pdf", "").replace(".PDF", "")
    # 去掉【...】前缀（如【销售专员】）
    name = re.sub(r'^【.*?】', '', name)
    name = re.sub(r'[【】]', '', name)
    # 按 _ 或空格分割
    parts = [p.strip() for p in re.split(r'[_\s]', name) if p.strip()]

    # 排除词：精确匹配
    excluded_exact = {'副本', '简历', '应聘', '求职'}
    # 排除词：包含即过滤（称谓、通用词）
    excluded_contains = {'先生', '小姐', '女士'}

    def _is_valid_name_part(part: str) -> bool:
        """检查一个部分是否像人名"""
        if part in excluded_exact:
            return False
        if any(bad in part for bad in excluded_contains):
            return False
        if re.match(r'\d+年毕业', part):
            return False
        # 过滤掉含"简历/求职/应聘"的词
        if any(bad in part for bad in ('简历', '求职', '应聘')):
            return False
        return True

    # 第一轮：找长度2-4个中文字符的部分
    for part in parts:
        if not _is_valid_name_part(part):
            continue
        cn_chars = re.findall(r'[一-龥]', part)
        if 2 <= len(cn_chars) <= 4:
            return part

    # 第二轮：更宽松，但限制长度（避免返回超长串）
    for part in parts:
        if not _is_valid_name_part(part):
            continue
        cn_chars = re.findall(r'[一-龥]', part)
        if len(cn_chars) >= 2 and len(cn_chars) <= 6:
            return part

    # 回退：从整个文件名中提取连续的中文字符片段
    # 不要直接返回 name.strip()，可能包含"女士""简历"等词
    cn_sequences = re.findall(r'[一-龥]{2,4}', name)
    for seq in cn_sequences:
        if not any(bad in seq for bad in excluded_contains):
            return seq

    # 彻底失败则返回空（让AI兜底）
    return ""


def _render_readonly_box(text: str, height: int = 120):
    """渲染自定义只读文本框（完全绕开 Streamlit disabled textarea 的样式陷阱）"""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    st.markdown(
        f"<div style='"
        f"height:{height}px;"
        f"overflow:auto;"
        f"padding:12px 16px;"
        f"background-color:#F5F0E8;"
        f"border:1.5px solid #DDD8CE;"
        f"border-radius:2px;"
        f"color:#1A2E22;"
        f"font-size:0.95rem;"
        f"line-height:1.6;"
        f"font-family:&quot;Noto Sans SC&quot;,&quot;PingFang SC&quot;,sans-serif;"
        f"white-space:pre-wrap;"
        f"word-break:break-word;"
        f"'>"
        f"{escaped}</div>",
        unsafe_allow_html=True
    )


def _format_score_remarks(scores: dict, total: float) -> str:
    """将评分详情格式化为备注文本（仅保留总分）"""
    if not scores:
        return ""
    return f"总分:{total:.2f}"


def process_candidates(files, transcripts, communicate_time, channel, intern_name=""):
    """处理候选人"""
    modules = get_modules()
    results = []

    for idx, file in enumerate(files):
        # 将UploadedFile保存到临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(file.getvalue())
            tmp_path = tmp_file.name

        try:
            # 1. 解析简历
            resume_data = modules["pdf_parser"].parse_resume(tmp_path, modules["ai_analyzer"])

            # 2. 姓名兜底：如果PDF没解析到，尝试从文件名提取
            if not resume_data.get("name"):
                name_from_file = _extract_name_from_filename(file.name)
                if name_from_file:
                    resume_data["name"] = name_from_file

            # 3. AI分析（无论是否有电话纪要，都基于简历进行分析评分）
            name_key = file.name.replace(".pdf", "")
            transcript = transcripts.get(name_key, "")
            analysis = modules["ai_analyzer"].analyze_phone_record(
                transcript, resume_data.get("raw_text", "")
            )

            # 4. 合并数据
            scores = analysis.get("scores", {})
            total_score = analysis.get("total_score", 0.0)
            candidate_data = {
                **resume_data,
                "channel": channel,
                "communicate_time": communicate_time,
                "description": analysis.get("description", ""),
                "score_details": scores,
                "score_total": total_score,
                "score_source": "ai",
                "ai_score_details": analysis.get("ai_score_details", scores),
                "ai_score_total": analysis.get("ai_score_total", total_score),
                "result": None,
                "phone_transcript": transcript,
                "intern_name": intern_name,
                "remarks": _format_score_remarks(scores, total_score)
            }

            # 5. 存入数据库
            candidate_id = modules["database"].insert_candidate(candidate_data)
            candidate_data["id"] = candidate_id
            results.append(candidate_data)

        except Exception as e:
            st.error(f"处理 {file.name} 时出错: {e}")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    if results:
        st.session_state["pending_candidates"] = results
        st.rerun()
    else:
        st.warning("没有成功处理任何候选人，请检查错误信息。")


def show_pending_results():
    """展示刚处理完成的候选人结果"""
    pending = st.session_state["pending_candidates"]

    st.success(f"成功处理 {len(pending)} 位候选人")

    # 展示 vision 模型不支持的照片识别错误提示
    vision_err = st.session_state.pop("_gender_vision_error", None)
    if vision_err:
        st.warning(vision_err, icon="📷")

    # 展示照片提取错误提示
    photo_err = st.session_state.pop("_photo_extract_error", None)
    if photo_err:
        st.info(photo_err, icon="📄")

    modules = get_modules()

    for candidate in pending:
        with st.container(border=True):
            # 头部信息
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{candidate.get('name') or '未识别'}**")
                st.caption(f"{candidate.get('school') or '学校未识别'} | {candidate.get('education') or '学历未识别'}")
            with col2:
                if candidate.get("score_total"):
                    st.metric("综合评分", f"{candidate.get('score_total', 0):.2f} / 5.0")

            # 详情展开
            with st.expander("查看详情"):
                info_col1, info_col2 = st.columns(2)
                with info_col1:
                    st.write(f"**手机：** {candidate.get('phone') or '无'}")
                    st.write(f"**专业：** {candidate.get('major') or '无'}")
                    st.write(f"**性别：** {candidate.get('gender') or '无'}")
                with info_col2:
                    st.write(f"**应届：** {candidate.get('is_fresh_grad') or '无'}")
                    st.write(f"**邮箱：** {candidate.get('email') or '无'}")
                    st.write(f"**渠道：** {candidate.get('channel') or '无'}")

                desc = candidate.get("description", "")
                st.markdown("**台账内容**")
                desc_key = f"pending_desc_{candidate['id']}"
                st.text_area(
                    "台账内容编辑",
                    value=desc,
                    key=desc_key,
                    height=120,
                    label_visibility="collapsed"
                )

                scores = candidate.get("score_details", {})
                if scores:
                    st.markdown("**评分详情**")
                    for dim_cfg in modules["scoring_dimensions"]:
                        dim_name = dim_cfg["dimension_name"]
                        weight = dim_cfg["weight"]
                        score = scores.get(dim_name, 0)
                        pct = (score / 5.0) * 100 if score else 0
                        st.markdown(
                            f"<div style='margin-bottom:10px;'>"
                            f"<div style='display:flex;justify-content:space-between;margin-bottom:4px;'>"
                            f"<span style='color:var(--text-inverse);font-size:0.9rem;'>{dim_name}</span>"
                            f"<span style='color:var(--accent);font-weight:600;'>{score:.1f}</span>"
                            f"</div>"
                            f"<div style='background:rgba(245,240,232,0.12);height:6px;border-radius:2px;'>"
                            f"<div style='background:var(--accent);height:100%;width:{pct}%;border-radius:2px;'></div>"
                            f"</div>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

            # 标记结果按钮
            current_result = candidate.get("result")
            c1, c2, c3 = st.columns(3)
            with c1:
                rec_label = "✅ 推荐" if current_result == "推荐" else "推荐"
                if st.button(rec_label, disabled=(current_result == "推荐"),
                             key=f"rec_{candidate['id']}", width="stretch"):
                    desc_key = f"pending_desc_{candidate['id']}"
                    edited_desc = st.session_state.get(desc_key, candidate.get("description", ""))
                    modules["database"].update_candidate(
                        candidate["id"], {"result": "推荐", "description": edited_desc}
                    )
                    candidate["result"] = "推荐"
                    st.toast("已标记为推荐", icon="✅")
                    st.rerun()
            with c2:
                elim_label = "❌ 淘汰" if current_result == "淘汰" else "淘汰"
                if st.button(elim_label, disabled=(current_result == "淘汰"),
                             key=f"elim_{candidate['id']}", width="stretch"):
                    desc_key = f"pending_desc_{candidate['id']}"
                    edited_desc = st.session_state.get(desc_key, candidate.get("description", ""))
                    modules["database"].update_candidate(
                        candidate["id"], {"result": "淘汰", "description": edited_desc}
                    )
                    candidate["result"] = "淘汰"
                    st.toast("已标记为淘汰", icon="❌")
                    st.rerun()
            with c3:
                if st.button("暂不标记", key=f"skip_{candidate['id']}", width="stretch"):
                    pass

    if st.button("继续添加新候选人", width="stretch"):
        st.session_state["pending_candidates"] = []
        st.rerun()


# ========== 标签页2：历史记录 ==========

def render_history():
    """历史记录页面"""
    st.markdown("### 历史记录")

    modules = get_modules()

    # 筛选和搜索
    col1, col2, _ = st.columns([1, 1, 2])
    with col1:
        result_filter = st.selectbox("筛选结果", ["全部", "推荐", "淘汰", "待审核"])
    with col2:
        search_keyword = st.text_input("搜索姓名/手机")
    st.divider()

    # 获取数据
    try:
        if search_keyword:
            candidates = modules["database"].search_candidates(search_keyword)
        elif result_filter and result_filter != "全部":
            filter_val = None if result_filter == "待审核" else result_filter
            candidates = modules["database"].get_all_candidates(filter_val)
        else:
            candidates = modules["database"].get_all_candidates()
    except Exception as e:
        st.error(f"查询失败: {e}")
        return

    # 待审核筛选
    if result_filter == "待审核":
        candidates = [c for c in candidates if not c.get("result")]

    # 统计卡片
    if candidates:
        total = len(candidates)
        recommend = sum(1 for c in candidates if c.get("result") == "推荐")
        eliminate = sum(1 for c in candidates if c.get("result") == "淘汰")
        pending = sum(1 for c in candidates if not c.get("result"))

        stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
        with stat_col1:
            st.metric("总计", total)
        with stat_col2:
            st.metric("推荐", recommend)
        with stat_col3:
            st.metric("淘汰", eliminate)
        with stat_col4:
            st.metric("待审核", pending)

    # 显示表格
    if not candidates:
        st.info("暂无数据")
        return

    df_data = [{
        "序号": c["id"],
        "岗位": "销售代表",
        "实习生": c.get("intern_name") or "—",
        "沟通时间": c.get("communicate_time") or "—",
        "姓名": c["name"] or "未识别",
        "手机号": c["phone"] or "—",
        "邮箱": c.get("email") or "—",
        "性别": c.get("gender") or "—",
        "出生年": c.get("birth_year") or "—",
        "学校": c["school"] or "—",
        "专业": c["major"] or "—",
        "学历": c["education"] or "—",
        "是否为应届生（2026届）": c.get("is_fresh_grad") or "—",
        "招聘渠道": c.get("channel") or "—",
        "推荐沟通情况": c.get("description") or "—",
        "备注": c.get("remarks") or "—"
    } for c in candidates]

    st.dataframe(df_data, width="stretch", hide_index=True)

    # 查看详情
    st.divider()
    selected_id = st.selectbox("选择候选人查看详情", [c["id"] for c in candidates])
    if selected_id:
        show_candidate_detail(selected_id)


def _format_candidate_row(c: dict) -> str:
    """将候选人信息格式化为表格行文本（制表符分隔），可直接粘贴到 Excel"""
    def _v(val):
        """空值显示为 —，保证 Excel 粘贴时每列都有内容"""
        if val is None:
            return "—"
        s = str(val).strip()
        return s if s else "—"

    fields = [
        _v(c.get("id")),
        "销售代表",
        _v(c.get("intern_name")),
        _v(c.get("communicate_time")),
        _v(c.get("name")),
        _v(c.get("phone")),
        _v(c.get("email")),
        _v(c.get("gender")),
        _v(c.get("birth_year")),
        _v(c.get("school")),
        _v(c.get("major")),
        _v(c.get("education")),
        _v(c.get("is_fresh_grad")),
        _v(c.get("channel")),
        _v(c.get("description")).replace("\n", " ").replace("\r", ""),
        _v(c.get("remarks"))
    ]
    return "\t".join(fields)


def _render_copy_button(text: str, btn_key: str):
    """使用前端 JS 复制到剪贴板，不依赖后端库，线上/线下均可用"""
    import json
    import streamlit.components.v1 as components

    safe_text = json.dumps(text, ensure_ascii=False)
    copy_html = f"""
    <div style="width:100%;">
        <button id="copy-btn-{btn_key}"
                style="width:100%;padding:0.4rem 1rem;border-radius:2px;background:#B87A4A;color:#F5F0E8;border:none;cursor:pointer;font-family:'Noto Sans SC','PingFang SC',sans-serif;font-size:0.85rem;font-weight:500;transition:background 0.2s;box-shadow:0 1px 2px rgba(0,0,0,0.15);"
                onmouseover="this.style.background='#A0683E'"
                onmouseout="this.style.background='#B87A4A'">
            复制
        </button>
        <script>
            (function() {{
                var btn = document.getElementById('copy-btn-{btn_key}');
                if (!btn) return;
                btn.addEventListener('click', function() {{
                    var t = {safe_text};
                    if (navigator.clipboard && navigator.clipboard.writeText) {{
                        navigator.clipboard.writeText(t).then(function() {{
                            btn.textContent = '已复制';
                            btn.style.background = '#2d5a3f';
                            setTimeout(function() {{
                                btn.textContent = '复制';
                                btn.style.background = '#B87A4A';
                            }}, 2000);
                        }}).catch(function() {{
                            fallbackCopy(t);
                        }});
                    }} else {{
                        fallbackCopy(t);
                    }}
                    function fallbackCopy(text) {{
                        var ta = document.createElement('textarea');
                        ta.value = text;
                        ta.style.position = 'fixed';
                        ta.style.opacity = '0';
                        document.body.appendChild(ta);
                        ta.select();
                        try {{
                            document.execCommand('copy');
                            btn.textContent = '已复制';
                            btn.style.background = '#2d5a3f';
                            setTimeout(function() {{
                                btn.textContent = '复制';
                                btn.style.background = '#B87A4A';
                            }}, 2000);
                        }} catch(e) {{
                            btn.textContent = '复制失败';
                            setTimeout(function() {{
                                btn.textContent = '复制';
                                btn.style.background = '#B87A4A';
                            }}, 2000);
                        }}
                        document.body.removeChild(ta);
                    }}
                }});
            }})();
        </script>
    </div>
    """
    components.html(copy_html, height=45)


def show_candidate_detail(candidate_id: int):
    """显示候选人详情（支持编辑和删除）"""
    modules = get_modules()
    try:
        candidate = modules["database"].get_candidate(candidate_id)
    except Exception as e:
        st.error(f"查询详情失败: {e}")
        return

    if not candidate:
        st.warning("候选人不存在")
        return

    name_col, ai_col, copy_col = st.columns([4, 1, 1])
    with name_col:
        st.subheader(f"{candidate['name'] or '未知'}")
    with ai_col:
        if st.button("🤖 AI识别", key=f"ai_fallback_btn_{candidate_id}", help="用AI重新提取简历中的基本信息"):
            raw_text = candidate.get("resume_raw_text", "")
            if raw_text and modules.get("ai_analyzer"):
                try:
                    with st.spinner("AI识别中..."):
                        ai_result = modules["ai_analyzer"].extract_missing_info(raw_text)
                    if ai_result and isinstance(ai_result, dict):
                        st.session_state[f"_ai_fallback_{candidate_id}"] = ai_result
                        st.toast("AI识别完成，已预填入编辑模式", icon="🤖")
                    else:
                        st.toast("AI未返回有效结果", icon="⚠️")
                except Exception as e:
                    st.toast(f"AI识别失败: {e}", icon="❌")
            else:
                st.toast("无简历原文或AI未配置", icon="⚠️")
            # 切换到编辑模式并刷新
            st.session_state[edit_key] = True
            st.rerun()
    with copy_col:
        _render_copy_button(
            _format_candidate_row(candidate),
            f"copy_btn_top_{candidate_id}"
        )

    # ========== 编辑模式 ==========
    edit_key = f"_edit_mode_{candidate_id}"
    if edit_key not in st.session_state:
        st.session_state[edit_key] = False

    # 应用AI fallback结果到编辑输入框（如果有）
    ai_fallback = st.session_state.pop(f"_ai_fallback_{candidate_id}", None)
    if ai_fallback and isinstance(ai_fallback, dict):
        edit_keys = [
            f"edit_name_{candidate_id}",
            f"edit_phone_{candidate_id}",
            f"edit_school_{candidate_id}",
            f"edit_major_{candidate_id}",
            f"edit_edu_{candidate_id}",
            f"edit_gender_{candidate_id}",
            f"edit_birth_{candidate_id}",
            f"edit_fresh_{candidate_id}",
            f"edit_channel_{candidate_id}",
            f"edit_intern_{candidate_id}",
            f"edit_remarks_{candidate_id}",
            f"edit_comm_time_{candidate_id}",
            f"edit_desc_{candidate_id}",
        ]
        for key in edit_keys:
            st.session_state.pop(key, None)
        # 写入AI提取的值
        if ai_fallback.get("name"):
            st.session_state[f"edit_name_{candidate_id}"] = ai_fallback["name"]
        if ai_fallback.get("phone"):
            st.session_state[f"edit_phone_{candidate_id}"] = ai_fallback["phone"]
        if ai_fallback.get("school"):
            st.session_state[f"edit_school_{candidate_id}"] = ai_fallback["school"]
        if ai_fallback.get("major"):
            st.session_state[f"edit_major_{candidate_id}"] = ai_fallback["major"]
        if ai_fallback.get("education"):
            st.session_state[f"edit_edu_{candidate_id}"] = ai_fallback["education"]
        if ai_fallback.get("gender"):
            st.session_state[f"edit_gender_{candidate_id}"] = ai_fallback["gender"]
        if ai_fallback.get("birth_year"):
            st.session_state[f"edit_birth_{candidate_id}"] = str(ai_fallback["birth_year"])
        if ai_fallback.get("is_fresh_grad"):
            st.session_state[f"edit_fresh_{candidate_id}"] = ai_fallback["is_fresh_grad"]
        if ai_fallback.get("email"):
            # email 不在编辑表单中，但可以放入备注提示
            pass

    if not st.session_state[edit_key]:
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**手机：** {candidate['phone'] or '无'}")
            st.write(f"**邮箱：** {candidate['email'] or '无'}")
            st.write(f"**学校：** {candidate['school'] or '无'}")
            st.write(f"**专业：** {candidate['major'] or '无'}")
        with col2:
            st.write(f"**学历：** {candidate['education'] or '无'}")
            st.write(f"**性别：** {candidate['gender'] or '无'}")
            st.write(f"**出生年份：** {candidate['birth_year'] or '无'}")
            st.write(f"**应届：** {candidate['is_fresh_grad'] or '无'}")

        st.write(f"**招聘渠道：** {candidate['channel'] or '无'} | **沟通时间：** {candidate['communicate_time'] or '无'}")
        st.write(f"**跟进实习生：** {candidate.get('intern_name') or '无'}")
        if candidate.get("remarks"):
            st.write(f"**备注：** {candidate['remarks']}")
    else:
        # 编辑模式
        with st.container(border=True):
            st.markdown("**编辑基本信息**")
            e_col1, e_col2 = st.columns(2)
            with e_col1:
                edit_name = st.text_input("姓名", value=candidate.get("name") or "", key=f"edit_name_{candidate_id}")
                edit_phone = st.text_input("手机", value=candidate.get("phone") or "", key=f"edit_phone_{candidate_id}")
                edit_school = st.text_input("学校", value=candidate.get("school") or "", key=f"edit_school_{candidate_id}")
                edit_major = st.text_input("专业", value=candidate.get("major") or "", key=f"edit_major_{candidate_id}")
            with e_col2:
                edit_edu = st.text_input("学历", value=candidate.get("education") or "", key=f"edit_edu_{candidate_id}")
                edit_gender = st.text_input("性别", value=candidate.get("gender") or "", key=f"edit_gender_{candidate_id}")
                edit_birth = st.text_input("出生年份", value=str(candidate.get("birth_year") or ""), key=f"edit_birth_{candidate_id}")
                edit_fresh = st.text_input("是否应届", value=candidate.get("is_fresh_grad") or "", key=f"edit_fresh_{candidate_id}")

            edit_channel = st.text_input("招聘渠道", value=candidate.get("channel") or "", key=f"edit_channel_{candidate_id}")
            edit_intern = st.text_input("跟进实习生", value=candidate.get("intern_name") or "", key=f"edit_intern_{candidate_id}")
            edit_remarks = st.text_input("备注", value=candidate.get("remarks") or "", key=f"edit_remarks_{candidate_id}")
            edit_comm_time = st.text_input("沟通时间", value=candidate.get("communicate_time") or "", key=f"edit_comm_time_{candidate_id}")
            edit_description = st.text_area("推荐沟通情况", value=candidate.get("description") or "", key=f"edit_desc_{candidate_id}", height=120)

            # ===== 人工评分编辑 =====
            st.markdown("**编辑评分**")
            current_scores = candidate.get("score_details", {}) or {}
            ai_scores = candidate.get("ai_score_details", {}) or {}
            edited_scores = {}
            score_total = 0.0

            with st.container(height=400):
                for dim_cfg in modules["scoring_dimensions"]:
                    dim_name = dim_cfg["dimension_name"]
                    weight = dim_cfg["weight"]
                    current_score = current_scores.get(dim_name, 0) or 0
                    edited_score = st.slider(
                        dim_name,
                        min_value=1.0,
                        max_value=5.0,
                        value=float(current_score) if current_score else 3.0,
                        step=0.5,
                        key=f"edit_score_{candidate_id}_{dim_name}",
                    )
                    edited_scores[dim_name] = edited_score
                    score_total += edited_score * weight

            score_total = round(score_total, 2)
            st.markdown(f"**加权总分：{score_total:.2f} / 5.0**")

            # 重置按钮
            reset_col, _ = st.columns([1, 3])
            with reset_col:
                if st.button("重置为 AI 评分", key=f"reset_ai_score_{candidate_id}"):
                    if ai_scores:
                        st.session_state[f"_reset_scores_{candidate_id}"] = True
                        st.rerun()

            # 检查是否有重置标记
            if st.session_state.pop(f"_reset_scores_{candidate_id}", False):
                for dim_cfg in modules["scoring_dimensions"]:
                    dim_name = dim_cfg["dimension_name"]
                    ai_val = ai_scores.get(dim_name, 3.0)
                    st.session_state[f"edit_score_{candidate_id}_{dim_name}"] = float(ai_val)
                st.rerun()

            save_col, cancel_col = st.columns([1, 1])
            with save_col:
                if st.button("保存修改", type="primary", key=f"save_edit_{candidate_id}", width="stretch"):
                    update_data = {
                        "name": edit_name,
                        "phone": edit_phone,
                        "school": edit_school,
                        "major": edit_major,
                        "education": edit_edu,
                        "gender": edit_gender,
                        "channel": edit_channel,
                        "is_fresh_grad": edit_fresh,
                        "intern_name": edit_intern,
                        "remarks": edit_remarks,
                        "communicate_time": edit_comm_time,
                        "description": edit_description,
                        "score_details": edited_scores,
                        "score_total": score_total,
                        "score_source": "manual",
                    }
                    if edit_birth.strip():
                        try:
                            update_data["birth_year"] = int(edit_birth.strip())
                        except ValueError:
                            pass
                    try:
                        modules["database"].update_candidate(candidate_id, update_data)
                        st.success("保存成功")
                        st.session_state[edit_key] = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"保存失败: {e}")
            with cancel_col:
                if st.button("取消", key=f"cancel_edit_{candidate_id}", width="stretch"):
                    st.session_state[edit_key] = False
                    # 取消时清除编辑输入框的值，下次编辑时恢复原始值
                    for _key in [
                        f"edit_name_{candidate_id}",
                        f"edit_phone_{candidate_id}",
                        f"edit_school_{candidate_id}",
                        f"edit_major_{candidate_id}",
                        f"edit_edu_{candidate_id}",
                        f"edit_gender_{candidate_id}",
                        f"edit_birth_{candidate_id}",
                        f"edit_fresh_{candidate_id}",
                        f"edit_channel_{candidate_id}",
                        f"edit_intern_{candidate_id}",
                        f"edit_remarks_{candidate_id}",
                        f"edit_comm_time_{candidate_id}",
                        f"edit_desc_{candidate_id}",
                    ]:
                        st.session_state.pop(_key, None)
                    st.rerun()

    # 台账描述
    desc = candidate.get("description", "")
    if desc:
        st.markdown("**台账内容**")
        _render_readonly_box(desc, height=150)

    # 评分
    scores = candidate.get("score_details", {})
    st.markdown("**综合评分**")
    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric("总分", f"{candidate['score_total'] or 0:.2f} / 5.0")
    with col2:
        for dim_cfg in modules["scoring_dimensions"]:
            dim_name = dim_cfg["dimension_name"]
            weight = dim_cfg["weight"]
            score = scores.get(dim_name, 0)
            pct = (score / 5.0) * 100 if score else 0
            st.markdown(
                f"<div style='margin-bottom:10px;'>"
                f"<div style='display:flex;justify-content:space-between;margin-bottom:4px;'>"
                f"<span style='color:var(--text-inverse);font-size:0.9rem;'>{dim_name}</span>"
                f"<span style='color:var(--accent);font-weight:600;'>{score:.1f}</span>"
                f"</div>"
                f"<div style='background:rgba(245,240,232,0.12);height:6px;border-radius:2px;'>"
                f"<div style='background:var(--accent);height:100%;width:{pct}%;border-radius:2px;'></div>"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True
            )

    # 操作按钮行
    st.markdown("**操作**")
    current_result = candidate.get("result")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        rec_label = "✅ 推荐" if current_result == "推荐" else "推荐"
        if st.button(rec_label, disabled=(current_result == "推荐"),
                     key=f"hist_rec_{candidate_id}", width="stretch"):
            try:
                modules["database"].update_candidate(
                    candidate_id, {"result": "推荐"}
                )
                st.toast("已标记为推荐", icon="✅")
                st.rerun()
            except Exception as e:
                st.error(f"标记失败: {e}")
    with c2:
        elim_label = "❌ 淘汰" if current_result == "淘汰" else "淘汰"
        if st.button(elim_label, disabled=(current_result == "淘汰"),
                     key=f"hist_elim_{candidate_id}", width="stretch"):
            try:
                modules["database"].update_candidate(
                    candidate_id, {"result": "淘汰"}
                )
                st.toast("已标记为淘汰", icon="❌")
                st.rerun()
            except Exception as e:
                st.error(f"标记失败: {e}")
    with c3:
        if st.button("编辑信息", key=f"hist_edit_{candidate_id}", width="stretch"):
            st.session_state[edit_key] = True
            st.rerun()
    with c4:
        # 删除需要确认
        del_confirm_key = f"_del_confirm_{candidate_id}"
        if del_confirm_key not in st.session_state:
            st.session_state[del_confirm_key] = False

        if not st.session_state[del_confirm_key]:
            if st.button("删除", key=f"hist_del_{candidate_id}", width="stretch"):
                st.session_state[del_confirm_key] = True
                st.rerun()
        else:
            if st.button("确认删除？", key=f"hist_del_confirm_{candidate_id}", width="stretch"):
                try:
                    modules["database"].delete_candidate(candidate_id)
                    st.success("已删除")
                    # 清除相关状态
                    if "pending_candidates" in st.session_state:
                        st.session_state["pending_candidates"] = [
                            c for c in st.session_state["pending_candidates"]
                            if c.get("id") != candidate_id
                        ]
                    st.rerun()
                except Exception as e:
                    st.error(f"删除失败: {e}")
            if st.button("取消", key=f"hist_del_cancel_{candidate_id}", width="stretch"):
                st.session_state[del_confirm_key] = False
                st.rerun()


# ========== 标签页3：台账导出 ==========

def render_export():
    """台账预览与导出页面"""
    st.markdown("### 台账预览与导出")

    modules = get_modules()

    # 获取数据
    try:
        candidates = modules["database"].get_all_candidates()
    except Exception as e:
        st.error(f"获取数据失败: {e}")
        return

    if not candidates:
        st.info("暂无数据可导出")
        return

    # 统计
    recommend_candidates = [c for c in candidates if c.get("result") == "推荐"]
    eliminate_candidates = [c for c in candidates if c.get("result") == "淘汰"]

    stat_col1, stat_col2 = st.columns(2)
    with stat_col1:
        st.metric("推荐台账", f"{len(recommend_candidates)} 人")
    with stat_col2:
        st.metric("淘汰台账", f"{len(eliminate_candidates)} 人")

    # Tab切换
    tab_recommend, tab_eliminate = st.tabs(["推荐台账", "淘汰台账"])

    with tab_recommend:
        show_table(recommend_candidates, "推荐")

    with tab_eliminate:
        show_table(eliminate_candidates, "淘汰")

    # 导出选项
    with st.container(border=True):
        st.markdown("#### 导出设置")
        col1, col2 = st.columns(2)
        with col1:
            include_scores = st.checkbox("包含评分详情", value=False)
        with col2:
            include_description = st.checkbox("包含沟通情况", value=True)

    # 导出按钮
    if st.button("导出Excel文件", type="primary", width="stretch"):
        try:
            filepath = modules["excel_exporter"].export(
                candidates,
                include_scores=include_scores,
                include_description=include_description
            )
            with open(filepath, "rb") as f:
                st.download_button(
                    label="点击下载Excel文件",
                    data=f,
                    file_name=os.path.basename(filepath),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width="stretch"
                )
        except Exception as e:
            st.error(f"导出失败: {e}")


# ========== 标签页4：系统配置 ==========

PROVIDER_PRESETS = {
    "OpenAI 官方": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "provider": "openai",
    },
    "硅基流动": {
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen2.5-72B-Instruct",
        "provider": "openai",
    },
    "DashScope (阿里云)": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "provider": "openai",
    },
    "其他自定义": {
        "base_url": "",
        "model": "",
        "provider": "openai",
    },
}


def render_settings():
    """AI 服务配置页面"""
    # 显示保存成功提示（刷新后保留一次）
    if st.session_state.pop("_config_saved", False):
        st.markdown(
            """
            <div style="
                text-align: center;
                padding: 1rem 1.5rem;
                margin-bottom: 1.5rem;
                background: rgba(74, 124, 89, 0.15);
                border: 1px solid rgba(74, 124, 89, 0.3);
                border-radius: 2px;
                color: #E4EDE6;
                font-family: 'Noto Sans SC', sans-serif;
                font-size: 0.95rem;
            ">
                配置已保存，可前往「新增候选人」页面使用 AI 分析功能
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("### 系统配置")
    st.markdown(
        "<p class='secondary-text' style='margin-bottom: 1.5rem;'>"
        "配置 AI 服务参数，信息会自动保存到本地文件，刷新浏览器不会丢失"
        "</p>",
        unsafe_allow_html=True
    )

    # ===== 用户标识管理 =====
    with st.container(border=True):
        st.markdown("#### 用户标识")
        st.markdown(
            "<p class='secondary-text' style='margin-bottom: 1rem;'>"
            "不同用户标识之间的配置和历史记录完全隔离。更换标识后将加载对应用户的数据。"
            "</p>",
            unsafe_allow_html=True
        )
        current_user = st.session_state.get("user_id", "")
        col_u1, col_u2 = st.columns([3, 1])
        with col_u1:
            new_user = st.text_input(
                "用户标识",
                value=current_user,
                key="_settings_user_id",
                placeholder="请输入用户标识",
            )
        with col_u2:
            st.markdown("<div style='height: 1.8rem;'></div>", unsafe_allow_html=True)
            if st.button("切换用户", type="primary", use_container_width=True, key="switch_user_btn"):
                if new_user and new_user.strip():
                    new_user = new_user.strip()
                    if new_user != current_user:
                        # 彻底清除所有会话状态，防止数据残留导致跨用户数据混淆
                        for key in list(st.session_state.keys()):
                            if key != "user_id":
                                del st.session_state[key]
                        st.session_state["user_id"] = new_user
                        st.success(f"已切换到用户：{new_user}")
                        st.rerun()
                else:
                    st.error("用户标识不能为空")

    # 读取当前配置（session_state → 用户文件 → 默认值）
    current = get_ai_config()

    # 根据当前 base_url 推断选中的服务商模板
    current_url = current.get("base_url", "") or ""
    preset_key = "OpenAI 官方"
    for name, preset in PROVIDER_PRESETS.items():
        if preset["base_url"] == current_url:
            preset_key = name
            break
    if not current_url and current.get("provider") == "dashscope":
        preset_key = "DashScope (阿里云)"

    with st.container(border=True):
        st.markdown("#### AI 服务配置")

        preset = st.selectbox(
            "选择服务商模板",
            options=list(PROVIDER_PRESETS.keys()),
            index=list(PROVIDER_PRESETS.keys()).index(preset_key),
            key="cfg_preset",
            help="选择后会自动填充推荐的 Base URL 和模型"
        )

        # 如果切换了模板，用默认值初始化 session_state 表单值
        selected_preset = PROVIDER_PRESETS[preset]
        if f"_preset_initialized_{preset}" not in st.session_state:
            st.session_state["cfg_model_val"] = selected_preset["model"]
            st.session_state["cfg_base_url_val"] = selected_preset["base_url"]
            st.session_state[f"_preset_initialized_{preset}"] = True
            # 清除其他模板的标记
            for k in list(st.session_state.keys()):
                if k.startswith("_preset_initialized_") and k != f"_preset_initialized_{preset}":
                    del st.session_state[k]

        # 用 session_state 管理值，避免 selectbox 切回时覆盖用户输入
        if "cfg_model_val" not in st.session_state:
            st.session_state["cfg_model_val"] = current.get("model", selected_preset["model"])
        if "cfg_base_url_val" not in st.session_state:
            st.session_state["cfg_base_url_val"] = current.get("base_url", selected_preset["base_url"]) or ""

        api_key = st.text_input(
            "API 密钥",
            value=current.get("api_key", ""),
            type="password",
            key="cfg_api_key",
            placeholder="sk-...",
            help="请填入真实的 API Key，不会显示在界面上"
        )

        model = st.text_input(
            "模型名称",
            value=st.session_state["cfg_model_val"],
            key="cfg_model_input",
            placeholder="gpt-4o-mini",
            help="例如：gpt-4o-mini、Qwen/Qwen2.5-72B-Instruct、qwen-plus"
        )
        # 同步回 session_state
        if model != st.session_state.get("cfg_model_val", ""):
            st.session_state["cfg_model_val"] = model

        base_url = st.text_input(
            "Base URL",
            value=st.session_state["cfg_base_url_val"],
            key="cfg_base_url_input",
            placeholder="https://api.openai.com/v1",
            help="OpenAI 兼容接口的服务地址，不要以斜杠结尾"
        )
        if base_url != st.session_state.get("cfg_base_url_val", ""):
            st.session_state["cfg_base_url_val"] = base_url

    # 保存按钮
    col_save, col_clear = st.columns([1, 1])
    with col_save:
        if st.button("保存配置", type="primary", width="stretch"):
            # 如果用户没有手动填写 base_url，回退到 preset 默认值
            final_base_url = base_url.strip() if base_url.strip() else selected_preset.get("base_url")
            cfg = {
                "provider": selected_preset["provider"],
                "api_key": api_key,
                "model": model,
                "base_url": final_base_url,
            }
            st.session_state["ai_config"] = cfg
            # 持久化到文件，刷新浏览器后配置不丢失
            save_user_config(cfg)
            # 清除缓存的 AI 分析器实例，使新配置立即生效
            init_analyzer.clear()
            init_parser.clear()
            st.session_state["_config_saved"] = True
            st.rerun()

    with col_clear:
        if st.button("清空当前配置", type="secondary", width="stretch"):
            if "ai_config" in st.session_state:
                del st.session_state["ai_config"]
            for k in list(st.session_state.keys()):
                if k.startswith("cfg_") or k.startswith("_preset_"):
                    del st.session_state[k]
            # 同时删除持久化的配置文件
            clear_user_config()
            init_analyzer.clear()
            init_parser.clear()
            st.info("已清空配置，将回退到文件默认值。")
            st.rerun()

    # 当前状态展示
    st.markdown("#### 当前配置状态")
    cfg = get_ai_config()
    status_col1, status_col2, status_col3 = st.columns(3)
    with status_col1:
        has_key = bool(cfg.get("api_key") and cfg["api_key"] != "your-api-key-here")
        st.metric(
            "API 密钥",
            "已填写" if has_key else "未配置",
        )
    with status_col2:
        st.metric("当前模型", cfg.get("model", "—"))
    with status_col3:
        url = cfg.get("base_url")
        st.metric("接口地址", "自定义" if url else "官方")

    st.divider()
    render_pricing_config()

    st.divider()
    render_api_billing()

    st.divider()
    render_scoring_config()

    st.divider()
    render_scoring_analysis()

    st.divider()
    render_data_management()


def render_scoring_config():
    """评分维度配置 UI"""
    st.markdown("### 评分维度配置")
    st.markdown(
        "<p class='secondary-text' style='margin-bottom: 1.5rem;'>"
        "配置 AI 评分的维度、权重和描述。权重之和必须等于 1.0，调整后点击保存生效"
        "</p>",
        unsafe_allow_html=True
    )

    db = get_database()
    dimensions = db.get_scoring_dimensions(active_only=False)

    # 用 session_state 管理编辑状态，避免每次交互重置
    state_key = "_scoring_dims_edit"
    if state_key not in st.session_state:
        st.session_state[state_key] = [
            {
                "_id": str(uuid.uuid4())[:8],
                "dimension_name": d["dimension_name"],
                "weight": float(d["weight"]),
                "description": d.get("description", ""),
                "sort_order": d.get("sort_order", 0),
                "is_active": bool(d.get("is_active", 1)),
            }
            for d in dimensions
        ]

    dims = st.session_state[state_key]

    # 权重总和提示
    total_weight = sum(d["weight"] for d in dims if d["is_active"])
    weight_color = "#4A7C59" if abs(total_weight - 1.0) < 0.001 else "#C75B39"
    st.markdown(
        f"<p style='color: {weight_color}; font-size: 0.9rem; margin-bottom: 1rem;'>"
        f"当前活跃维度权重之和：<strong>{total_weight:.3f}</strong>"
        f"{' ✓' if abs(total_weight - 1.0) < 0.001 else '（必须等于 1.0）'}"
        f"</p>",
        unsafe_allow_html=True
    )

    # 列头
    st.markdown("#### 维度列表")
    header_cols = st.columns([3, 2, 4, 1])
    with header_cols[0]:
        st.markdown("<p style='color: #B8B2A6; font-size: 0.8rem; margin-bottom: 0.2rem;'>维度名称</p>", unsafe_allow_html=True)
    with header_cols[1]:
        st.markdown("<p style='color: #B8B2A6; font-size: 0.8rem; margin-bottom: 0.2rem;'>权重</p>", unsafe_allow_html=True)
    with header_cols[2]:
        st.markdown("<p style='color: #B8B2A6; font-size: 0.8rem; margin-bottom: 0.2rem;'>描述（用于 AI Prompt）</p>", unsafe_allow_html=True)
    with header_cols[3]:
        st.markdown("<p style='color: #B8B2A6; font-size: 0.8rem; margin-bottom: 0.2rem;'>操作</p>", unsafe_allow_html=True)

    # 修复 number_input 在深色主题下文字颜色问题
    st.markdown("""
    <style>
    [data-testid="stNumberInput"] input {
        color: #1A2E22 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    to_remove = []

    for i, dim in enumerate(dims):
        uid = dim["_id"]
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 2, 4, 1])
            with col1:
                new_name = st.text_input(
                    "维度名称",
                    value=dim["dimension_name"],
                    key=f"dim_name_{uid}",
                    label_visibility="collapsed",
                    placeholder="维度名称",
                )
                dim["dimension_name"] = new_name.strip()
            with col2:
                new_weight = st.number_input(
                    "权重",
                    value=float(dim["weight"]),
                    min_value=0.0,
                    max_value=1.0,
                    step=0.05,
                    format="%.2f",
                    key=f"dim_weight_{uid}",
                    label_visibility="collapsed",
                )
                dim["weight"] = new_weight
            with col3:
                new_desc = st.text_input(
                    "描述",
                    value=dim.get("description", ""),
                    key=f"dim_desc_{uid}",
                    label_visibility="collapsed",
                    placeholder="维度描述（用于 AI Prompt）",
                )
                dim["description"] = new_desc.strip()
            with col4:
                st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
                if st.button("🗑️", key=f"dim_del_{uid}", help="删除此维度"):
                    to_remove.append(i)

    # 执行删除
    for idx in reversed(to_remove):
        dims.pop(idx)
        st.rerun()

    # 添加新维度
    col_add, _ = st.columns([1, 3])
    with col_add:
        if st.button("➕ 添加维度", type="secondary"):
            dims.append({
                "_id": str(uuid.uuid4())[:8],
                "dimension_name": "",
                "weight": 0.0,
                "description": "",
                "sort_order": len(dims),
                "is_active": True,
            })
            st.rerun()

    # 操作按钮
    col_save, col_reset = st.columns([1, 1])
    with col_save:
        if st.button("保存配置", type="primary", key="scoring_save"):
            valid, err = validate_scoring_weights(dims)
            if not valid:
                st.error(f"保存失败：{err}")
            else:
                # 重新计算 sort_order
                for idx, d in enumerate(dims):
                    d["sort_order"] = idx
                db.save_scoring_config(dims)
                st.success("评分配置已保存")
                st.rerun()

    with col_reset:
        if st.button("恢复默认", type="secondary", key="scoring_reset"):
            defaults = db.get_default_dimensions()
            db.save_scoring_config(defaults)
            st.session_state[state_key] = [
                {
                    "_id": str(uuid.uuid4())[:8],
                    "dimension_name": d["dimension_name"],
                    "weight": float(d["weight"]),
                    "description": d.get("description", ""),
                    "sort_order": d.get("sort_order", 0),
                    "is_active": bool(d.get("is_active", True)),
                }
                for d in defaults
            ]
            st.success("已恢复默认配置")
            st.rerun()


def render_scoring_analysis():
    """迭代分析 UI —— AI 评分 vs 人工评分偏差统计"""
    st.markdown("### 评分迭代分析")
    st.markdown(
        "<p class='secondary-text' style='margin-bottom: 1.5rem;'>"
        "基于人工修正过的评分数据，分析 AI 评分的系统性偏差，优化权重配置"
        "</p>",
        unsafe_allow_html=True
    )

    db = get_database()
    all_candidates = db.get_all_candidates()
    # 只取有人工修正的
    manual_candidates = [
        c for c in all_candidates
        if c.get("score_source") in ("manual", "mixed")
        and c.get("ai_score_details")
        and c.get("score_details")
    ]

    if len(manual_candidates) < 1:
        st.info(
            "暂无人工修正数据。请在候选人详情页的「编辑」模式下修改评分并保存，"
            "此处将自动展示 AI 与人工评分的偏差分析。"
        )
        return

    # 计算各维度偏差
    dimensions = db.get_scoring_dimensions(active_only=True)
    dim_names = [d["dimension_name"] for d in dimensions]

    deviations = {}
    counts = {}
    ai_values = {}
    manual_values = {}

    for dim in dim_names:
        deviations[dim] = []
        ai_values[dim] = []
        manual_values[dim] = []

    for c in manual_candidates:
        ai_scores = c.get("ai_score_details", {})
        man_scores = c.get("score_details", {})
        for dim in dim_names:
            ai_s = ai_scores.get(dim)
            man_s = man_scores.get(dim)
            if ai_s is not None and man_s is not None:
                try:
                    deviations[dim].append(float(ai_s) - float(man_s))
                    ai_values[dim].append(float(ai_s))
                    manual_values[dim].append(float(man_s))
                except (ValueError, TypeError):
                    pass

    # 统计表格
    st.markdown(f"**基于 {len(manual_candidates)} 条人工修正数据**")

    stats_data = []
    for dim in dim_names:
        vals = deviations.get(dim, [])
        if vals:
            avg_dev = sum(vals) / len(vals)
            # 标准差
            if len(vals) > 1:
                mean = avg_dev
                variance = sum((v - mean) ** 2 for v in vals) / len(vals)
                std_dev = variance ** 0.5
            else:
                std_dev = 0.0
            stats_data.append({
                "维度": dim,
                "样本数": len(vals),
                "平均偏差 (AI-人工)": round(avg_dev, 2),
                "标准差": round(std_dev, 2),
            })

    if stats_data:
        import pandas as pd
        st.dataframe(pd.DataFrame(stats_data), hide_index=True, use_container_width=True)

        # 偏差柱状图（用 Altair 精确控制颜色）
        chart_df = pd.DataFrame({
            "维度": [s["维度"] for s in stats_data],
            "平均偏差": [s["平均偏差 (AI-人工)"] for s in stats_data],
        })
        try:
            import altair as alt
            bar_chart = alt.Chart(chart_df).mark_bar(color="#D4A574").encode(
                x=alt.X("维度", sort=None),
                y=alt.Y("平均偏差", title="平均偏差 (AI - 人工)"),
                tooltip=["维度", "平均偏差"],
            )
            st.altair_chart(bar_chart, use_container_width=True)
        except Exception:
            # 如果 Altair 不可用，回退到简单表格
            st.dataframe(chart_df, hide_index=True, use_container_width=True)

        # 优化建议
        st.markdown("#### 优化建议")
        suggestions = []
        for s in stats_data:
            dim = s["维度"]
            avg_dev = s["平均偏差 (AI-人工)"]
            if abs(avg_dev) > 0.5:
                direction = "偏高" if avg_dev > 0 else "偏低"
                suggestions.append(
                    f"- **{dim}**：AI 评分系统性地 {direction}（平均偏差 {avg_dev:+.2f}），"
                    f"建议调整该维度的 AI Prompt 描述或权重"
                )

        if suggestions:
            for sg in suggestions:
                st.markdown(sg)
        else:
            st.success("各维度偏差均在可接受范围内（≤0.5），AI 评分较为准确。")

        # 基于数据的一键权重调整建议
        st.markdown("#### 数据驱动的权重调整")
        st.caption("根据人工修正数据，自动建议新的权重配置（实验性）")

        if st.button("生成权重建议", type="secondary", key="gen_weight_suggestion"):
            # 简单策略：如果 AI 在某维度持续偏高，降低权重；持续偏低，提高权重
            # 使用 sigmoid 映射偏差到权重调整系数
            import math
            suggested = []
            for d in dimensions:
                dim_name = d["dimension_name"]
                current_w = d["weight"]
                # 找对应偏差
                avg_dev = 0.0
                for s in stats_data:
                    if s["维度"] == dim_name:
                        avg_dev = s["平均偏差 (AI-人工)"]
                        break
                # 调整因子：偏差为正（AI偏高）→ 降低权重；偏差为负 → 提高权重
                # 用 tanh 限制调整幅度在 ±30% 内
                factor = 1.0 - math.tanh(avg_dev * 1.5) * 0.3
                suggested.append({
                    "dimension_name": dim_name,
                    "weight": current_w * factor,
                    "description": d.get("description", ""),
                    "sort_order": d.get("sort_order", 0),
                    "is_active": True,
                })

            # 归一化，使总和为 1.0
            total = sum(s["weight"] for s in suggested)
            if total > 0:
                for s in suggested:
                    s["weight"] = round(s["weight"] / total, 4)

            st.markdown("**建议权重：**")
            suggestion_df = pd.DataFrame([
                {"维度": s["dimension_name"], "当前权重": d["weight"], "建议权重": s["weight"]}
                for s, d in zip(suggested, dimensions)
            ])
            st.dataframe(suggestion_df, hide_index=True, use_container_width=True)

            if st.button("应用建议权重", type="primary", key="apply_suggested_weights"):
                for idx, s in enumerate(suggested):
                    s["sort_order"] = idx
                db.save_scoring_config(suggested)
                st.success("已应用建议权重")
                st.rerun()
    else:
        st.warning("人工修正数据与当前维度不匹配，无法生成统计。")


def render_pricing_config():
    """模型单价配置 UI"""
    st.markdown("### 模型单价配置")
    st.markdown(
        "<p class='secondary-text' style='margin-bottom: 1.5rem;'>"
        "配置各模型的输入/输出单价（元 / 百万 tokens），用于估算 API 费用。"
        "未配置价格的模型，费用将显示为 0。"
        "</p>",
        unsafe_allow_html=True,
    )

    # 加载当前配置
    pricing_cfg = load_pricing_config()
    state_key = "_pricing_edit"
    if state_key not in st.session_state:
        st.session_state[state_key] = [
            {"_id": str(uuid.uuid4())[:8], "model": k, "input": float(v.get("input", 0)), "output": float(v.get("output", 0))}
            for k, v in pricing_cfg.items()
        ]

    models = st.session_state[state_key]

    # 显示已有模型配置
    for i, item in enumerate(models):
        cols = st.columns([3, 2, 2, 1])
        with cols[0]:
            item["model"] = st.text_input(
                "模型名称", value=item["model"], key=f"pricing_model_{item['_id']}"
            )
        with cols[1]:
            item["input"] = st.number_input(
                "输入单价", value=float(item["input"]), min_value=0.0, step=0.1,
                format="%.2f", key=f"pricing_input_{item['_id']}"
            )
        with cols[2]:
            item["output"] = st.number_input(
                "输出单价", value=float(item["output"]), min_value=0.0, step=0.1,
                format="%.2f", key=f"pricing_output_{item['_id']}"
            )
        with cols[3]:
            st.markdown("<div style='height: 1.8rem;'></div>", unsafe_allow_html=True)
            if st.button("删除", key=f"pricing_del_{item['_id']}"):
                models.pop(i)
                st.rerun()

    col_add, col_save = st.columns([1, 1])
    with col_add:
        if st.button("+ 添加模型", type="secondary", use_container_width=True):
            models.append({"_id": str(uuid.uuid4())[:8], "model": "", "input": 0.0, "output": 0.0})
            st.rerun()

    with col_save:
        if st.button("保存价格配置", type="primary", use_container_width=True):
            data = {}
            for item in models:
                name = item["model"].strip()
                if name:
                    data[name] = {
                        "input": float(item["input"]),
                        "output": float(item["output"]),
                    }
            save_pricing_config(data)
            st.success("价格配置已保存")


def render_api_billing():
    """API 使用账单 UI"""
    st.markdown("### API 使用账单")

    from datetime import datetime, timedelta

    db = get_database()

    # 日期范围选择
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "开始日期",
            value=datetime.now() - timedelta(days=30),
            key="billing_start",
        )
    with col2:
        end_date = st.date_input(
            "结束日期",
            value=datetime.now(),
            key="billing_end",
        )

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # 查询数据
    summary = db.get_api_usage_summary(start_str, end_str)
    details = db.get_api_usage_details(start_str, end_str)

    # 汇总卡片
    total_calls = sum(s["call_count"] for s in summary)
    total_tokens = sum(s["total_tokens"] for s in summary)
    total_cost = sum(s["total_cost"] for s in summary)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("总调用次数", f"{total_calls}")
    with c2:
        st.metric("总 Token 消耗", f"{total_tokens:,}")
    with c3:
        st.metric("估算总费用", f"¥{total_cost:.4f}")

    if not summary:
        st.info("所选时间段内暂无 API 使用记录。")
        return

    # 按功能分组表格
    st.markdown("#### 按功能汇总")
    summary_data = []
    for s in summary:
        summary_data.append({
            "功能": s["feature"],
            "调用次数": s["call_count"],
            "输入 Tokens": s["prompt_tokens"],
            "输出 Tokens": s["completion_tokens"],
            "总 Tokens": s["total_tokens"],
            "估算费用": f"¥{s['total_cost']:.4f}",
        })
    st.dataframe(summary_data, use_container_width=True, hide_index=True)

    # 明细列表
    with st.expander("查看调用明细"):
        detail_data = []
        for d in details:
            detail_data.append({
                "时间": d["timestamp"],
                "功能": d["feature"],
                "模型": d["model"],
                "输入 Tokens": d["prompt_tokens"],
                "输出 Tokens": d["completion_tokens"],
                "总 Tokens": d["total_tokens"],
                "估算费用": f"¥{d['estimated_cost']:.6f}",
            })
        st.dataframe(detail_data, use_container_width=True, hide_index=True)

    # 未配置价格模型提示
    used_models = {d["model"] for d in details}
    priced_models = set(load_pricing_config().keys())
    unpriced = used_models - priced_models
    if unpriced:
        st.warning(
            f"以下模型尚未配置单价，费用计为 0：{', '.join(unpriced)}。"
            "请在上方「模型单价配置」中补全。"
        )


def render_data_management():
    """数据管理 UI —— 导出/导入数据库"""
    st.markdown("### 数据管理")
    st.markdown(
        "<p class='secondary-text' style='margin-bottom: 1.5rem;'>"
        "导出数据库用于备份，或在重新部署后导入恢复数据。"
        "不同用户的数据库文件相互独立。"
        "</p>",
        unsafe_allow_html=True,
    )

    # 获取当前用户的数据库路径（与 get_database 逻辑保持一致）
    user_id = st.session_state.get("user_id", "").strip()
    if user_id:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", user_id)
        db_path = f"data/recruitment_{safe_id}.db"
    else:
        db_path = "data/recruitment.db"

    # ===== 导出 =====
    with st.container(border=True):
        st.markdown("#### 导出数据")
        if os.path.exists(db_path):
            file_size = os.path.getsize(db_path)
            with open(db_path, "rb") as f:
                db_bytes = f.read()
            st.download_button(
                label=f"下载数据库备份（{file_size / 1024:.1f} KB）",
                data=db_bytes,
                file_name=os.path.basename(db_path),
                mime="application/octet-stream",
                key="export_db_btn",
            )
            st.caption(f"当前数据库路径：{db_path}")
        else:
            st.info("暂无数据库文件（可能还没有录入候选人数据）。")

    # ===== 导入 =====
    with st.container(border=True):
        st.markdown("#### 导入数据")
        uploaded = st.file_uploader(
            "选择数据库文件（.db）",
            type=["db"],
            key="import_db_uploader",
            help="上传之前导出的 .db 文件，将覆盖当前用户的数据。操作前建议先导出备份。",
        )
        if uploaded is not None:
            # 先写入临时文件做校验
            with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                tmp.write(uploaded.getvalue())
                tmp_path = tmp.name

            is_valid = False
            missing_cols = []
            try:
                conn = sqlite3.connect(tmp_path)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='candidates'"
                )
                is_valid = cursor.fetchone() is not None

                if is_valid:
                    # 校验必需列是否存在
                    cursor.execute("PRAGMA table_info(candidates)")
                    columns = {row[1] for row in cursor.fetchall()}
                    required = {
                        "name", "phone", "email", "gender", "birth_year",
                        "school", "major", "education", "is_fresh_grad",
                        "channel", "communicate_time", "description",
                        "score_total", "score_details", "result"
                    }
                    missing_cols = list(required - columns)
                    if missing_cols:
                        is_valid = False

                conn.close()
            except Exception:
                is_valid = False

            if not is_valid:
                if missing_cols:
                    st.error(
                        f"数据库文件版本不兼容，缺少必需字段：{', '.join(missing_cols)}"
                    )
                else:
                    st.error("上传的文件不是有效的招聘助手数据库（缺少 candidates 表）。")
                os.remove(tmp_path)
                return

            # 校验通过，执行导入
            if st.button("确认导入并覆盖当前数据", type="primary", key="confirm_import_btn"):
                # 备份当前数据库
                if os.path.exists(db_path):
                    backup_path = (
                        db_path + ".backup." + datetime.now().strftime("%Y%m%d_%H%M%S")
                    )
                    shutil.copy2(db_path, backup_path)
                    st.info(f"已自动备份现有数据库：{os.path.basename(backup_path)}")

                try:
                    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
                    with open(db_path, "wb") as f:
                        f.write(uploaded.getvalue())
                    st.success("数据库导入成功！请刷新页面以加载新数据。")
                except Exception as e:
                    st.error(f"导入失败：{e}")
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)


# ========== 通用表格组件 ==========

def show_table(candidates: List[Dict], result_type: str):
    """显示表格"""
    if not candidates:
        st.info("暂无数据")
        return

    if result_type == "推荐":
        columns = [
            "序号", "岗位", "实习生", "沟通时间", "姓名", "手机号", "邮箱",
            "性别", "出生年", "学校", "专业", "学历", "是否为应届生（2026届）",
            "招聘渠道", "推荐沟通情况", "备注"
        ]
    else:
        columns = [
            "序号", "实习生", "沟通时间", "姓名", "手机号", "邮箱",
            "性别", "出生年", "学校", "专业", "学历", "是否是应届生（2026届）",
            "招聘渠道", "沟通状态", "沟通详情", "（淘汰模板）"
        ]

    df_data = []
    for c in candidates:
        if result_type == "推荐":
            row = {
                "序号": c["id"],
                "岗位": "销售代表",
                "实习生": c.get("intern_name") or "",
                "沟通时间": c.get("communicate_time") or "",
                "姓名": c["name"] or "",
                "手机号": c["phone"] or "",
                "邮箱": c.get("email") or "",
                "性别": c.get("gender") or "",
                "出生年": c.get("birth_year") or "",
                "学校": c["school"] or "",
                "专业": c["major"] or "",
                "学历": c["education"] or "",
                "是否为应届生（2026届）": c.get("is_fresh_grad") or "",
                "招聘渠道": c.get("channel") or "",
                "推荐沟通情况": c.get("description") or "",
                "备注": c.get("remarks") or ""
            }
        else:
            row = {
                "序号": c["id"],
                "实习生": c.get("intern_name") or "",
                "沟通时间": c.get("communicate_time") or "",
                "姓名": c["name"] or "",
                "手机号": c["phone"] or "",
                "邮箱": c.get("email") or "",
                "性别": c.get("gender") or "",
                "出生年": c.get("birth_year") or "",
                "学校": c["school"] or "",
                "专业": c["major"] or "",
                "学历": c["education"] or "",
                "是否是应届生（2026届）": c.get("is_fresh_grad") or "",
                "招聘渠道": c.get("channel") or "",
                "沟通状态": c.get("result") or "待审核",
                "沟通详情": c.get("description") or "",
                "（淘汰模板）": ""
            }
        df_data.append(row)

    st.dataframe(df_data, width="stretch", hide_index=True)

    # 显示沟通情况
    with st.expander("查看沟通情况详情"):
        for c in candidates:
            st.markdown(f"**{c['name']}**")
            _render_readonly_box(c.get("description", "无"), height=100)
            st.divider()


if __name__ == "__main__":
    main()
