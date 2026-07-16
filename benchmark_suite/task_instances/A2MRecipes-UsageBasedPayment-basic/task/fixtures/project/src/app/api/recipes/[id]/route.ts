import { NextResponse } from 'next/server';
import { recipes } from '@/data/recipes';

/**
 * GET /api/recipes/[id] - full recipe detail.
 */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const recipeId = parseInt(id, 10);
  const recipe = recipes.find((r) => r.id === recipeId);

  if (!recipe) {
    return NextResponse.json(
      { success: false, error: '食谱不存在' },
      { status: 404 }
    );
  }

  return NextResponse.json(
    {
      success: true,
      data: recipe,
    },
    { status: 200 }
  );
}
