import { NextRequest, NextResponse } from 'next/server';
import { recipes } from '@/data/recipes';

/**
 * GET /api/recipes/random - 随机推荐
 *
 * 仅返回预览信息（无食材/步骤），详情需 A2M 付费解锁
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);

  const age = searchParams.get('age');
  const count = Math.min(
    parseInt(searchParams.get('count') || '3', 10),
    10
  );

  let pool = [...recipes];
  if (age) {
    const ageNum = parseInt(age, 10);
    pool = pool.filter((r) => ageNum >= r.ageMonthStart && ageNum <= r.ageMonthEnd);
  }

  // Fisher-Yates shuffle + 取前 count 个
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }

  const selected = pool.slice(0, count);

  // 返回预览数据
  const previewData = selected.map(
    ({ ingredients, steps, ...preview }) => ({
      ...preview,
      locked: true,
    })
  );

  return NextResponse.json({
    success: true,
    data: previewData,
    total: previewData.length,
  });
}
