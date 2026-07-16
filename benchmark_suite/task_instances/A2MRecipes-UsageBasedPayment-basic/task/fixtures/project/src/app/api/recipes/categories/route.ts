import { NextResponse } from 'next/server';
import { recipes } from '@/data/recipes';

export async function GET() {
  // 提取所有分类
  const categoryMap = new Map<string, number>();
  const ageMap = new Map<string, number>();

  recipes.forEach((r) => {
    categoryMap.set(r.category, (categoryMap.get(r.category) || 0) + 1);

    const ageKey = r.ageRange;
    ageMap.set(ageKey, (ageMap.get(ageKey) || 0) + 1);
  });

  const categories = Array.from(categoryMap.entries()).map(([name, count]) => ({
    name,
    count,
  }));

  const ageRanges = Array.from(ageMap.entries()).map(([range, count]) => ({
    range,
    count,
  }));

  // 收集所有标签
  const tagSet = new Set<string>();
  recipes.forEach((r) => r.tags.forEach((t) => tagSet.add(t)));

  return NextResponse.json({
    success: true,
    data: {
      categories,
      ageRanges,
      tags: Array.from(tagSet).sort(),
      totalRecipes: recipes.length,
    },
  });
}