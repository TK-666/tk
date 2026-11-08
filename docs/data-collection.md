# 美术作品样本数据收集

## 数据来源与筛选

演示数据来自 [芝加哥艺术学院公开 API](https://api.artic.edu/docs/) 的作品检索接口。采集时只选取馆方元数据中 `is_public_domain=true`、`artwork_type_title=Painting`、有 `image_id` 的记录；风格直接使用馆方 `style_title`，不根据画面自行猜测。图片来自同馆 [IIIF 图片接口](https://api.artic.edu/docs/#images)，按馆方建议串行请求并限速。馆方的公有领域标记和具体使用条件应以其[图片授权说明](https://www.artic.edu/image-licensing)及条款为准。

当前样本共 **500 件**，包括印象派 120、国风 115、日本绘画 65、南亚绘画 52、后印象派 35、喜马拉雅绘画 30、写实主义 28、文艺复兴 20、民间艺术 12、现代主义 12、巴洛克 5、新古典主义 5、点彩派 1。国风、日本绘画、南亚绘画和喜马拉雅绘画对应馆方的文化或地区分类。每件记录保留馆方作品编号、原始标题、艺术家、创作年代、材料、原始风格、题材词、作品网页和 API 地址、IIIF 地址，以及本地图片的 SHA-256。原始数据位于 [`data/artworks.json`](../data/artworks.json)，图片位于 `data/images/`。导入后系统使用本地 `/api/uploads/` 图片地址，可在断网情况下展示。

## 标签处理

- `style`：馆方 `style_title` 的中文名称。没有馆方风格值的作品不进入样本。
- `topic`：优先映射馆方 `subject_titles`，同时识别馆方标题中明确的题材词，例如肖像、山水、动物和宗教。500 件作品中，384 件有题材标签，共 21 个题材标签。
- `medium`：从馆方 `medium_display` 同时提取技法和材质，例如油画、纸本、绢本和金彩。一件作品可有多个媒介标签，目前共 12 个。
- `era`：用馆方 `date_start` 计算世纪，原始年代文字仍保留在元数据和作品简介中。

映射规则写在 [`scripts/collect_artworks.py`](../scripts/collect_artworks.py)，可复核和重新运行。新增 JPEG 采用馆方推荐的 843 像素宽度，首批图片的宽度不超过 1200 像素。导入时再生成 WebP 封面。作品简介组合馆方提供的事实字段，并附馆方作品页面链接。

## 导入与复现

项目根目录执行：

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\import_artworks.py
```

先按 README 初始化数据库。导入脚本会核对每张图片的 SHA-256，在当前配置的数据库中创建缺失标签和公开作品，并把图片复制到运行时上传目录。同一作品以馆方编号识别。已有作品可用以下命令补充清单中缺少的标签，原有标签和作品资料会保留。

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\import_artworks.py --update-tags
```

如果修改了标签映射，可以直接用已保存的馆方元数据更新清单，无需重新下载图片。

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\collect_artworks.py --refresh-tags
```

若要采集馆方数据，在联网环境运行：

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\collect_artworks.py
```

采集脚本保留现有记录和图片，分页检索并按风格补足配额，同时按馆方作品编号、图片编号和图片哈希去重。提交前应核查新增元数据和图片。用户浏览、点赞、收藏和评分属于系统运行时产生的行为数据，**没有从外部网站获取或伪造**。

## 样本边界

这是一组用于功能演示和初步推荐观察的小样本，集中于馆藏中的历史绘画，不能代表所有美术风格。它尚未覆盖赛博朋克、抽象等风格，也不能单靠这些作品衡量真实用户的推荐效果。若论文需要效果指标，应另行设计经同意的用户交互实验，说明样本量、评价方法和局限。
