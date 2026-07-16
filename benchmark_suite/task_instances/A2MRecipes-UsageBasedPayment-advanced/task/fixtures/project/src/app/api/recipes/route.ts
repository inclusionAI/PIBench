import { NextRequest, NextResponse } from 'next/server';
import { recipes } from '@/data/recipes';

/**
 * GET /api/recipes - 食谱列表
 *
 * 列表仅返回预览信息（无食材/步骤），详情需 A2M 付费解锁
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);

  const age = searchParams.get('age');
  const category = searchParams.get('category');
  const tag = searchParams.get('tag');
  const search = searchParams.get('search');
  const page = parseInt(searchParams.get('page') || '1', 10);
  const limit = Math.min(parseInt(searchParams.get('limit') || '20', 10), 50);

  // 筛选
  let filtered = [...recipes];

  if (age) {
    const ageNum = parseInt(age, 10);
    filtered = filtered.filter(
      (r) => ageNum >= r.ageMonthStart && ageNum <= r.ageMonthEnd
    );
  }

  if (category) {
    filtered = filtered.filter(
      (r) => r.category.toLowerCase() === category.toLowerCase()
    );
  }

  if (tag) {
    filtered = filtered.filter((r) =>
      r.tags.some((t) => t.toLowerCase().includes(tag.toLowerCase()))
    );
  }

  if (search) {
    const q = search.toLowerCase();
    filtered = filtered.filter(
      (r) =>
        r.name.toLowerCase().includes(q) ||
        r.tags.some((t) => t.toLowerCase().includes(q)) ||
        r.nutrition.toLowerCase().includes(q) ||
        r.ingredients.some((i) => i.toLowerCase().includes(q))
    );
  }

  // 分页
  const total = filtered.length;
  const totalPages = Math.ceil(total / limit);
  const start = (page - 1) * limit;
  const paged = filtered.slice(start, start + limit);

  // 返回预览数据（不含 ingredients/steps，标记 locked）
  const previewData = paged.map(
    ({ ingredients, steps, ...preview }) => ({
      ...preview,
      locked: true,
    })
  );

  return NextResponse.json({
    success: true,
    data: previewData,
    pagination: {
      page,
      limit,
      total,
      totalPages,
      hasMore: page < totalPages,
    },
  });
}
