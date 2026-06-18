# 英语语法练习系统

一个基于 Flask 和 LLM 的英语语法练习与中考题训练 Web 应用。

## 功能特性

### 📚 语法练习模块
- **多年级支持**：小学 1-5 年级分级练习
- **多种题型**：
  - 选择题 (choice)
  - 填空题 (fill)
  - 判断题 (judge)
  - 改错题 (correction)
- **知识点练习**：支持按知识点筛选题目
- **智能去重**：避免重复练习相同题目

### 🎯 中考题练习模块
- **选择题**：历年中考英语选择题练习
- **完形填空**：中考完形填空专项训练
- **相似题生成**：AI 生成同知识点相似题目
- **本地题库**：基于 JSON 的本地题库，快速响应

### 🤖 AI 智能功能
- **题目生成**：LLM 自动生成语法练习题
- **智能批改**：自动批改用户答案
- **详细讲解**：生成题目解析和知识点讲解
- **相似题推荐**：根据知识点生成相似练习题

### 📊 学习统计
- 错题本功能
- 学习数据统计

## 技术栈

- **后端**：Flask 3.1.1
- **AI 服务**：OpenAI API（支持自定义 API 端点）
- **题库**：JSON 格式本地存储
- **前端**：HTML/CSS/JavaScript（模板渲染）

## 快速开始

### 环境要求

- Python 3.8+
- pip

### 安装步骤

1. **克隆项目**
   ```bash
   git clone <repository-url>
   cd grammar
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **配置环境变量**

   复制 `.env.example` 为 `.env` 并填写配置：
   ```bash
   cp .env.example .env
   ```

   编辑 `.env` 文件：
   ```env
   LLM_API_BASE_URL=https://api.openai.com/v1
   LLM_API_KEY=your-api-key-here
   LLM_MODEL_NAME=gpt-4o-mini
   ```

4. **准备题库数据**

   确保以下文件存在：
   - `choice.json` - 中考选择题库
   - `cloze.json` - 中考完形填空题库
   - `answers.json` - 题目答案数据

5. **启动应用**
   ```bash
   python app.py
   ```

   应用将在 `http://0.0.0.0:5000` 启动

### 调试模式

启用调试模式（注意：可能影响日志输出）：
```bash
FLASK_DEBUG=1 python app.py
```

## 项目结构

```
grammar/
├── app.py                 # Flask 主应用
├── config.py              # 配置管理
├── llm_service.py         # LLM 服务封装
├── question_bank.py       # 题库管理
├── fetch_answers.py       # 答案获取工具
├── requirements.txt       # Python 依赖
├── .env.example          # 环境变量示例
├── choice.json           # 中考选择题库
├── cloze.json            # 中考完形填空题库
├── answers.json          # 题目答案
└── templates/            # HTML 模板
    ├── index.html        # 首页
    ├── grammar.html      # 语法练习页
    ├── quiz.html         # 练习页面
    ├── zhongkao.html     # 中考练习首页
    ├── zhongkao_quiz.html # 中考练习页
    ├── wrong_questions.html # 错题本
    └── stats.html        # 统计页面
```

## API 接口

### 语法练习 API

#### 获取题目
```http
POST /api/questions
Content-Type: application/json

{
  "grade": 1,
  "question_type": "choice",
  "knowledge_point": "时态",
  "count": 1,
  "history": []
}
```

#### 批改答案
```http
POST /api/grade
Content-Type: application/json

{
  "question": {...},
  "user_answer": "A",
  "question_type": "choice"
}
```

#### 获取讲解
```http
POST /api/explain
Content-Type: application/json

{
  "question": {...},
  "user_answer": "A",
  "correct_answer": "B",
  "is_correct": false,
  "question_type": "choice"
}
```

### 中考题练习 API

#### 获取中考题
```http
POST /api/zhongkao/questions
Content-Type: application/json

{
  "source_type": "choice",
  "count": 1
}
```

#### 批改中考题
```http
POST /api/zhongkao/grade
Content-Type: application/json

{
  "question_id": "q001",
  "user_answer": "A",
  "source_type": "choice"
}
```

#### 获取中考题讲解
```http
POST /api/zhongkao/explain
Content-Type: application/json

{
  "question_id": "q001",
  "user_answer": "A",
  "is_correct": false,
  "source_type": "choice"
}
```

#### 生成相似题
```http
POST /api/zhongkao/similar
Content-Type: application/json

{
  "question": {...},
  "knowledge_point_id": "kp001",
  "knowledge_point_name": "时态",
  "source_type": "choice"
}
```

## 部署说明

### 子路径部署

应用支持子路径部署（如 `/englishtest`），通过环境变量配置：

```bash
export APPLICATION_ROOT=/englishtest
python app.py
```

Nginx 配置示例：
```nginx
location /englishtest/ {
    proxy_pass http://127.0.0.1:5000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### 生产环境建议

1. 使用 Gunicorn 或 uWSGI 作为 WSGI 服务器
2. 配置 Nginx 反向代理
3. 关闭调试模式：`FLASK_DEBUG=0`
4. 使用环境变量管理敏感配置
5. 配置日志收集和监控

## 开发指南

### 日志系统

应用使用 Python 标准日志库，所有日志输出到 stdout：
- INFO 级别：请求信息、LLM 调用统计
- WARNING 级别：参数错误
- ERROR 级别：异常信息（包含堆栈跟踪）

### LLM 调用统计

每次 LLM 调用都会记录：
- 调用函数名
- 使用的模型
- 耗时（秒）
- Token 消耗（输入/输出/总计）

### 题库格式

选择题格式示例：
```json
[
  {
    "id": "q001",
    "stem": "题目内容",
    "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"],
    "correctAnswer": "A",
    "knowledgePointId": "kp001",
    "knowledgePointName": "时态"
  }
]
```