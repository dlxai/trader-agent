# 项目启动指南

## 项目结构

```
trader-agent/
├── packages/
│   ├── backend-py/      # Python FastAPI 后端
│   ├── frontend/        # React + Vite 前端
│   └── strategy-py/     # Python 策略模块
├── docker/              # Docker 配置
└── docs/                # 文档
```

---

## 后端启动 (Python)

### 1. 安装依赖

```bash
cd packages/backend-py

# 安装 Poetry (如果还没有)
pip install poetry

# 安装依赖
poetry install
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，设置必要的配置
```

### 3. 数据库迁移

```bash
# 创建数据库 (如果使用 SQLite 则跳过)
# 运行迁移
poetry run alembic upgrade head
```

### 4. 启动服务

```bash
# 开发模式 (带热重载)
poetry run uvicorn src.main:app --reload --port 3001

# 生产模式
poetry run uvicorn src.main:app --host 0.0.0.0 --port 3001
```

### 5. 验证启动

```bash
# 健康检查
curl http://localhost:3001/health
```

---

## 前端启动

### 1. 安装依赖

```bash
cd packages/frontend
npm install
```

### 2. 开发模式

```bash
npm run dev
# 默认启动在 http://localhost:5173
```

### 3. 构建生产版本

```bash
npm run build
# 输出到 dist/ 目录
```

### 4. 预览生产构建

```bash
npm run preview
```

---

## 策略模块 (strategy-py)

```bash
cd packages/strategy-py

# 安装依赖
pip install -r requirements.txt

# 运行策略
python -m src.main
```

---

## Docker 启动 (推荐生产环境)

```bash
# 构建并启动所有服务
docker-compose up --build

# 后台运行
docker-compose up -d
```

---

## 常见问题

### 端口冲突

- 后端默认端口: 3001
- 前端开发服务器: 5173

如果端口被占用，修改相应的配置文件。

### 数据库连接失败

检查 `.env` 文件中的 `DATABASE_URL` 配置。

### 前端无法连接后端

检查前端配置文件中的 API 地址是否正确。

---

## 登录逻辑

后端使用 JWT 认证：

1. 用户登录: `POST /auth/login`
2. 获取 JWT token
3. 后续请求在 Header 中携带: `Authorization: Bearer <token>`
4. Token 过期后需要重新登录或使用 refresh token

详见 `packages/backend-py/src/routers/auth.py`
