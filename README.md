# VocabVault - 英语词汇宝库

一个优雅的英语词汇学习管理应用，使用 Free Dictionary API / MiniMax 提供单词查询、释义、例句等功能。

## 功能特点

- 🔍 **智能查询**：输入单词或短语，获取详细释义（单词优先走 Free Dictionary API，短语或未命中时走 MiniMax）
- 🎯 **详细解释**：音标、词性、释义、例句、发音
- 📝 **收藏功能**：保存学习过的词汇
- 🏷️ **标签管理**：预设与自定义标签，支持筛选查找
- 💾 **数据持久化**：LocalStorage 本地存储

## 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 可选：配置 MiniMax（查短语或 Free Dictionary 未命中时使用）
export MINIMAX_API_KEY=your_key

# 运行
python server.py
```

浏览器打开 http://localhost:3000

## 部署到 Render（Web Service）

1. 将本仓库推送到 GitHub
2. 在 Render 创建 **Web Service**，连接该仓库
3. 配置：
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python server.py`
4. 环境变量（可选）：`MINIMAX_API_KEY` = 你的 MiniMax API Key

部署后访问根路径即可使用；收藏、标签、筛选等与前端同源，均可正常使用。

## 技术栈

- 前端：HTML5, CSS3, Vanilla JavaScript
- 后端：Python Flask
- 查词：Free Dictionary API（单词）+ MiniMax（短语/回退）

## 许可证

MIT
