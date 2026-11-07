# 基于风格标签的美术作品欣赏智能推荐系统

Vue 3 + Element Plus 前端、Flask API 和 MySQL 数据模型。当前 `main` 提供统一的可运行框架，供作品标签、用户交互、推荐算法和论文文档分支继续开发。

## 项目结构

```text
backend/app/api/       统一 /api 接口：认证、作品、交互、推荐、管理
backend/app/models.py  用户、作品、标签、收藏、点赞、评分、行为日志和推荐配置
frontend/src/views/    用户端与管理员端页面
docs/                  架构、接口和分支协作约定
```

## 本地启动

需要 Python 3.11+、Node.js 20.19+，正式部署使用 MySQL 8。开发时默认使用 SQLite，方便先验证流程。

1. 复制 `.env.example` 为 `.env`，将 `SECRET_KEY` 改为随机长字符串，以便重启后保持登录会话。若使用 MySQL，将 `DATABASE_URL` 设为 `mysql+pymysql://用户:密码@主机:3306/数据库?charset=utf8mb4`，并先创建数据库。
2. 进入 `backend`，创建虚拟环境，执行 `pip install -r requirements.txt`。
3. 执行 `flask --app run init-db`，再执行 `flask --app run run --debug`。API 默认位于 `http://127.0.0.1:5000/api`。
4. 进入 `frontend`，在 PowerShell 执行 `npm.cmd install` 和 `npm.cmd run dev`，打开终端显示的地址。Vite 会代理 `/api` 到本地 Flask 服务。
5. 需要管理员时，设置临时环境变量 `ADMIN_PASSWORD`（至少 8 字符），在 `backend` 执行 `flask --app run create-admin admin`，然后清除该环境变量。

示例 PowerShell 命令：

```powershell
Copy-Item .env.example .env
Set-Location backend
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app run init-db
.\.venv\Scripts\python.exe -m flask --app run run --debug
```

另开终端：

```powershell
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

## 检查与测试

在 `backend` 执行 `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`，在 `frontend` 执行 `npm.cmd run build`。测试覆盖账号、管理员、作品与标签、交互和推荐。MySQL 表结构可在无凭据情况下编译检查；实库测试需要明确提供 `MYSQL_TEST_PASSWORD`，会建立并清理独立的临时数据库。

## 当前覆盖范围

| 任务书需求 | `main` 现状 |
| --- | --- |
| 用户注册、登录、资料、偏好标签 | 基础 API 和页面已接通 |
| 作品录入、封面/原图上传、发布与下架 | 管理界面支持分页检索、上传预览和自动生成封面；发布前要求原图 |
| 风格、题材、媒介、年代标签 | 数据模型、分类维护和四类筛选接口与页面已建立 |
| 浏览、关键词搜索、作品详情 | 基础 API 和页面已接通 |
| 点赞、收藏、评分、浏览记录 | 数据模型与接口已建立，详情页可操作 |
| 个性化、热门、最新推荐 | 基础标签匹配和轻量 ItemCF 已建立；算法评估待做 |
| 用户管理、统计、推荐权重 | 基础 API 和管理页面已建立，管理员可重置密码 |
| 自动化测试、压测、部署、论文及过程文档 | 已有基础流程测试；完整测试、压测、部署和论文材料仍待完成 |

接口与数据约定见 [docs/architecture.md](docs/architecture.md)。`init-db` 仅用于首次本地建表；后续变更数据库结构时需引入正式迁移方案，不要在已有数据的库上依赖 `create_all` 更新表。
