# 项目上下文

## 项目简介
宝宝辅食食谱推荐 API，为 0-3 岁宝宝提供科学营养的辅食食谱推荐。内置 100 道专业辅食食谱，支持按月龄、分类、标签、关键词等多维度筛选。

## 技术栈

- **Framework**: Next.js 16 (App Router)
- **Core**: React 19
- **Language**: TypeScript 5
- **UI 组件**: shadcn/ui (基于 Radix UI)
- **Styling**: Tailwind CSS 4

## 目录结构

```
├── src/
│   ├── app/
│   │   ├── api/
│   │   │   └── recipes/
│   │   │       ├── route.ts           # GET /api/recipes - 食谱列表
│   │   │       ├── [id]/route.ts      # GET /api/recipes/[id] - 食谱详情
│   │   │       ├── random/route.ts    # GET /api/recipes/random - 随机推荐
│   │   │       └── categories/route.ts # GET /api/recipes/categories - 分类信息
│   │   ├── layout.tsx
│   │   ├── page.tsx                   # 前端页面
│   │   └── globals.css
│   ├── data/
│   │   └── recipes.ts                 # 100道辅食食谱数据
│   └── components/ui/
├── public/
├── .coze
└── package.json
```

## API 接口说明

### GET /api/recipes
食谱列表查询，支持参数：
- `age` - 宝宝月龄（数字）
- `category` - 分类（主食/蔬菜/肉类/汤羹/点心/水果/蛋白质）
- `tag` - 标签筛选
- `search` - 关键词搜索（名称、食材、标签、营养）
- `page` - 页码（默认1）
- `limit` - 每页数量（默认20，最大50）

### GET /api/recipes/[id]
获取单个食谱完整详情（含食材清单和制作步骤）

### GET /api/recipes/random
随机推荐食谱
- `age` - 可选，按指定月龄推荐
- `count` - 推荐数量（默认3，最大10）

### GET /api/recipes/categories
获取分类信息、月龄段、标签列表

## 数据说明

- 100道食谱覆盖 6-36 个月龄段
- 按月龄分为 5 个阶段：6-8个月、8-12个月、12-18个月、18-24个月、24-36个月
- 每条食谱包含名称、分类、月龄、食材、步骤、营养说明、制作时间、难度、标签

## 开发规范

- 包管理：仅使用 pnpm
- TypeScript strict 模式
- 新增 API 路由时同步更新本文档
- 修改食谱数据时注意保持完整性
