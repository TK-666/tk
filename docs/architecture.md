# 架构与协作约定

## 模块边界

- `backend/app/api/auth.py`：普通用户认证、资料、偏好风格。
- `backend/app/api/artworks.py`：公开标签与作品检索、详情。
- `backend/app/api/interactions.py`：收藏、点赞、评分及行为日志。
- `backend/app/api/recommendations.py`：推荐接口入口和参数校验；`backend/app/services/recommendation.py` 负责标签匹配、ItemCF、热门与最新排序。
- `backend/app/api/admin.py`：管理员作品、标签、用户、统计、权重与上传。
- `frontend/src/api.js`：统一请求和错误处理；组件不直接拼接后端域名。

功能分支可在各自模块内迭代。新增 API 应保持 `/api` 前缀、JSON 响应、错误结构 `{ "error": "..." }`，并在对应页面和本文件更新约定。

## 数据与权限

使用服务端会话 Cookie；`user` 和 `admin` 两种角色。公开访问作品和标签；交互与偏好需要登录；管理接口需要管理员。停用用户无法继续调用受保护接口。图片上传只接受 JPEG、PNG、WebP，默认限制 10 MB。

作品状态：`draft` 草稿、`published` 公开、`archived` 下架。普通用户只会看到 `published`。标签类别：`style`、`topic`、`medium`、`era`。

发布作品前必须填写原图地址。图片地址接受 HTTP(S) 或站内路径；管理员上传原图时，接口会保留原图并自动生成最长边不超过 1200 像素的 WebP 封面。封面也可以单独上传。单次上传限制 10 MB，图片尺寸不超过 4000 万像素，最长边不超过 12000 像素。

## 主要接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/health` | 服务状态 |
| POST | `/api/auth/register`, `/api/auth/login`, `/api/auth/logout` | 账号 |
| GET/PATCH | `/api/auth/me` | 当前用户资料 |
| PUT | `/api/auth/preferences` | 风格标签 ID 数组 |
| GET | `/api/tags` | 标签列表，可用 `category` 过滤 |
| GET | `/api/artworks` | `q`、`style`、`topic`、`medium`、`era`、`page`、`per_page` |
| GET | `/api/artworks/{id}` | 作品详情，登录时记一次浏览 |
| GET/PUT | `/api/artworks/{id}/interaction` | 点赞、收藏、评分 |
| GET | `/api/me/favorites` | 收藏夹 |
| GET | `/api/recommendations` | `kind=personal|hot|latest`，`limit=1..50`（默认 20） |
| GET/POST/PATCH | `/api/admin/artworks[/{id}]` | 作品管理；列表支持 `q`、`status`、`page`、`per_page` |
| DELETE | `/api/admin/artworks/{id}` | 永久删除作品及其标签关联和用户互动记录 |
| POST/PATCH/DELETE | `/api/admin/tags[/{id}]` | 标签管理 |
| GET/PATCH | `/api/admin/users[/{id}]` | 用户管理 |
| DELETE | `/api/admin/users/{id}` | 永久删除普通用户及其偏好和互动记录 |
| GET | `/api/admin/stats` | 数量统计 |
| GET/PUT | `/api/admin/settings` | 推荐权重 |
| POST | `/api/admin/uploads` | 上传图片，表单字段 `file` 与 `purpose=original|cover`；原图上传返回 `url` 和 `cover_url` |

交互请求示例：`{"action":"favorite","active":true}` 或 `{"action":"rate","score":5}`。个性化推荐先利用用户明确选择的风格标签，再从浏览、当前点赞、当前收藏和高评分构建用户与作品的正向行为矩阵；物品协同过滤对共同被正向交互的作品计算余弦相似度，并结合标签、热门度及管理员置顶进行排序。浏览次数设上限，取消点赞或收藏后不再把旧操作日志当作正向信号；低评分作品不出现在个人推荐中。已互动作品排在未互动作品之后，作品不足时仍可作为补充。接口返回 `strategy`（访客热门、冷启动、仅偏好或混合推荐）与每件作品的 `recommendation_reason`。热门榜依据当前有效行为排序，最新榜按上传时间排序。当前为演示规模的请求时计算实现，大数据量需离线计算、缓存、压测和效果评估。

推荐权重、公式与边界见 [recommendation.md](recommendation.md)。

## 集成检查

1. 合并前先检查分支是否真的有提交，并确认工作区没有未提交的改动。
2. 保持模型字段、状态值、标签类别、API 路径与前端约定一致。
3. 在空库运行初始化、注册、管理员建号、作品发布、用户交互与推荐的完整流程。
4. 补充迁移、功能测试、压测和 MySQL 部署验证后，再宣称满足任务书的最终交付要求。
