# 基于风格标签的美术作品欣赏智能推荐系统

Vue 3 + Element Plus 前端、Flask API 和 MySQL 数据模型。当前 `main` 已集成项目环境、作品与标签管理、用户交互和推荐功能，供后续测试、部署与论文工作使用。

## 项目结构

```text
backend/app/api/       统一 /api 接口：认证、作品、交互、推荐、管理
backend/app/models.py  用户、作品、标签、收藏、点赞、评分、行为日志和推荐配置
frontend/src/views/    用户端与管理员端页面
docs/                  架构、接口和分支协作约定
data/                  馆方公有领域作品样本清单与图片
scripts/collect_artworks.py  样本采集脚本
scripts/import_artworks.py   样本导入脚本
```

## 本地启动

需要 Python 3.11+，以及 Node.js 20.19+（20.x）或 22.12+。以下命令从当前分支的项目根目录执行。首次运行会建立本工作树专用的 Python 虚拟环境、安装依赖、生成带随机会话密钥的 `.env`，并初始化 SQLite。已有 `.env` 会继续使用。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

如果 Python 启动器不可用，在命令末尾加上 `-PythonPath` 和可用的 `python.exe` 完整路径。`-ExecutionPolicy Bypass` 只应用于这次启动的 PowerShell 进程。

打开两个 PowerShell 终端，分别在项目根目录运行下列命令：

```powershell
# 终端 1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Backend

# 终端 2
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 Frontend
```

打开 `http://127.0.0.1:5173/`。`http://127.0.0.1:5173/api/health` 应返回 `{"status":"ok"}`。如果与其他工作树并行运行，给两条命令传相同的 `-BackendPort`，并给前端单独传 `-FrontendPort`。默认端口分别为 5000 和 5173。

SQLite 文件在 `backend/instance/artworks.db`，本地上传默认在 `backend/instance/uploads/`。需要管理员时，在 `backend` 目录设置进程环境变量 `ADMIN_PASSWORD`（至少 8 字符），运行 `.\.venv\Scripts\python.exe -m flask --app run create-admin admin`，再清除该环境变量。

### 导入作品样本

数据库初始化后，在项目根目录运行 `.\backend\.venv\Scripts\python.exe .\scripts\import_artworks.py`。仓库附有 46 件馆方标记为公有领域的绘画样本及图片；导入可重复执行，不会重复创建作品。样本来源、筛选和标签映射见 [docs/data-collection.md](docs/data-collection.md)。

### 使用 MySQL 8

先在 MySQL 创建独立数据库（建议 `utf8mb4`）和该数据库专用账号。在项目根目录的 `.env` 中把 `DATABASE_URL` 改为下面的连接串，替换账号、密码和库名。密码含 `@`、`#` 等保留字符时先做 URL 编码。

```dotenv
DATABASE_URL=mysql+pymysql://art_user:password@127.0.0.1:3306/art_recommend?charset=utf8mb4
```

如果要先安装依赖再编辑连接配置，在初始化脚本后加 `-SkipDatabase`。配置完成后在 `backend` 运行 `.\.venv\Scripts\python.exe -m flask --app run init-db`，再启动服务。

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
| 个性化、热门、最新推荐 | 风格偏好、浏览/点赞/收藏/评分行为与余弦相似度 ItemCF 已接入；冷启动和推荐原因可见，效果评估待做 |
| 用户管理、统计、推荐权重 | 基础 API 和管理页面已建立，管理员可重置密码 |
| 自动化测试、压测、部署、论文及过程文档 | 已有基础流程测试；完整测试、压测、部署和论文材料仍待完成 |

接口与数据约定见 [docs/architecture.md](docs/architecture.md)。`init-db` 仅用于首次本地建表；后续变更数据库结构时需引入正式迁移方案，不要在已有数据的库上依赖 `create_all` 更新表。

推荐算法的输入、权重和冷启动规则见 [docs/recommendation.md](docs/recommendation.md)。
