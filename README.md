# 招聘助手 — 线上版

基于 Streamlit 的在线招聘管理工具，支持 PDF 简历解析、AI 智能分析、候选人评分和 Excel 台账导出。

## 快速部署（Streamlit Community Cloud）

1. **Fork / 复制本项目到你的 GitHub 仓库**

2. **注册并登录** [share.streamlit.io](https://share.streamlit.io)

3. **连接 GitHub 仓库**，选择本项目

4. **配置 Secrets**：在 Streamlit Cloud 后台点击 App → Settings → Secrets，填入：

   ```toml
   [siliconflow]
   api_key = "你的API密钥"
   base_url = "https://api.siliconflow.cn/v1"
   model = "Qwen/Qwen3-30B-A3B-Instruct-2507"
   ```

5. **点击 Deploy**，等待 1-2 分钟即可访问

## 本地开发

```bash
pip install -r requirements.txt
streamlit run app.py
```

本地开发时如需配置 AI 密钥，可创建 `.streamlit/secrets.toml`（已加入 .gitignore，不会提交）：

```toml
[siliconflow]
api_key = "你的API密钥"
base_url = "https://api.siliconflow.cn/v1"
model = "Qwen/Qwen3-30B-A3B-Instruct-2507"
```

## ⚠️ 数据持久化说明

Streamlit Community Cloud 的文件系统是无状态的，每次重启后 `data/recruitment.db` 会重置。

如需持久化数据，请：
- **方案A**：定期导出 Excel 备份（应用内支持）
- **方案B**：迁移到云数据库（如 Supabase PostgreSQL），修改 `modules/database.py` 的数据库连接即可

## 与桌面版（v3）的区别

| 特性 | v3 桌面版 | v4 线上版 |
|------|----------|----------|
| 运行方式 | PyInstaller 本地打包 | Streamlit Cloud / 服务器 |
| AI 配置 | `ai_config.json` 文件 | `st.secrets` / 环境变量 |
| 数据库 | 本地 SQLite（持久化） | 本地 SQLite（重启丢失） |
| 访问 | 仅本机 | 任何有浏览器的设备 |
| 维护 | 需手动更新 | Git push 自动部署 |
