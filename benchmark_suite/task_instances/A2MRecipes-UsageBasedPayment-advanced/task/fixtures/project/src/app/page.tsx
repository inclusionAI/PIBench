'use client';

import { useEffect, useState } from 'react';

interface RecipePreview {
  id: number;
  name: string;
  category: string;
  ageRange: string;
  ageMonthStart: number;
  ageMonthEnd: number;
  nutrition: string;
  cookingTime: number;
  difficulty: string;
  tags: string[];
  locked?: boolean;
}

interface RecipeDetail {
  id: number;
  name: string;
  category: string;
  ageRange: string;
  ingredients: string[];
  steps: string[];
  nutrition: string;
  cookingTime: number;
  difficulty: string;
  tags: string[];
}

interface CategoryInfo {
  name: string;
  count: number;
}

interface AgeRangeInfo {
  range: string;
  count: number;
}

interface CategoriesData {
  categories: CategoryInfo[];
  ageRanges: AgeRangeInfo[];
  tags: string[];
  totalRecipes: number;
}

export default function HomePage() {
  const [recipes, setRecipes] = useState<RecipePreview[]>([]);
  const [categories, setCategories] = useState<CategoriesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedAge, setSelectedAge] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [randomRecipes, setRandomRecipes] = useState<RecipePreview[]>([]);
  const [showRandom, setShowRandom] = useState(false);

  // A2M 支付流状态
  const [detailRecipe, setDetailRecipe] = useState<RecipeDetail | null>(null);
  const [paymentNeeded, setPaymentNeeded] = useState<string | null>(null);
  const [paymentProof, setPaymentProof] = useState('');
  const [unlockLoading, setUnlockLoading] = useState(false);
  const [unlockError, setUnlockError] = useState('');
  const [currentRecipeId, setCurrentRecipeId] = useState<number | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        const [recipeRes, catRes] = await Promise.all([
          fetch('/api/recipes?limit=12'),
          fetch('/api/recipes/categories'),
        ]);
        const recipeData = await recipeRes.json();
        const catData = await catRes.json();
        if (recipeData.success) setRecipes(recipeData.data);
        if (catData.success) setCategories(catData.data);
      } catch (e) {
        console.error('获取数据失败', e);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const handleSearch = async () => {
    setLoading(true);
    setShowRandom(false);
    try {
      const params = new URLSearchParams();
      if (selectedAge) params.set('age', selectedAge);
      if (selectedCategory) params.set('category', selectedCategory);
      if (searchTerm) params.set('search', searchTerm);
      params.set('limit', '20');

      const res = await fetch(`/api/recipes?${params.toString()}`);
      const data = await res.json();
      if (data.success) setRecipes(data.data);
    } finally {
      setLoading(false);
    }
  };

  const handleRandom = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (selectedAge) params.set('age', selectedAge);
      params.set('count', '3');
      const res = await fetch(`/api/recipes/random?${params.toString()}`);
      const data = await res.json();
      if (data.success) {
        setRandomRecipes(data.data);
        setShowRandom(true);
      }
    } finally {
      setLoading(false);
    }
  };

  /** 打开食谱详情 - 触发 A2M 支付流 */
  const openDetail = async (recipe: RecipePreview) => {
    setDetailRecipe(null);
    setPaymentNeeded(null);
    setPaymentProof('');
    setUnlockError('');
    setCurrentRecipeId(recipe.id);

    try {
      const res = await fetch(`/api/recipes/${recipe.id}`);
      if (res.status === 402) {
        // A2M 支付需要 - 解析 Payment-Needed Header
        const paymentHeader = res.headers.get('payment-needed');
        if (paymentHeader) {
          setPaymentNeeded(paymentHeader);
        }
        // 也尝试读取响应体
        try {
          const body = await res.json();
          if (body.paymentNeeded) {
            setPaymentNeeded(body.paymentNeeded);
          }
        } catch {
          // 忽略 JSON 解析失败
        }
      } else if (res.ok) {
        const data = await res.json();
        if (data.success) {
          setDetailRecipe(data.data);
        }
      }
    } catch (e) {
      console.error('获取食谱详情失败', e);
      setUnlockError('网络请求失败，请重试');
    }
  };

  /** 提交 Payment-Proof 解锁食谱 */
  const handleUnlock = async () => {
    if (!paymentProof.trim() || !currentRecipeId) return;
    setUnlockLoading(true);
    setUnlockError('');

    try {
      const res = await fetch(`/api/recipes/${currentRecipeId}`, {
        headers: {
          'Payment-Proof': paymentProof.trim(),
        },
      });

      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          setDetailRecipe(data.data || data.content);
          setPaymentNeeded(null);
        } else {
          setUnlockError(data.message || '解锁失败');
        }
      } else if (res.status === 402) {
        setUnlockError('支付凭证无效，请确认已完成支付');
      } else {
        const data = await res.json().catch(() => ({}));
        setUnlockError(data.message || `请求失败 (${res.status})`);
      }
    } catch (e) {
      console.error('解锁请求失败', e);
      setUnlockError('网络请求失败，请重试');
    } finally {
      setUnlockLoading(false);
    }
  };

  /** 关闭弹窗 */
  const closeDetail = () => {
    setDetailRecipe(null);
    setPaymentNeeded(null);
    setPaymentProof('');
    setUnlockError('');
    setCurrentRecipeId(null);
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-orange-50 via-white to-orange-50">
      {/* Header */}
      <header className="bg-orange-500 text-white">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-4xl">👶</span>
            <h1 className="text-3xl sm:text-4xl font-bold">
              宝宝辅食食谱大全
            </h1>
          </div>
          <p className="text-lg text-orange-100 max-w-2xl">
            专为 0-3 岁宝宝设计的营养辅食食谱平台，内置 100 道专业辅食食谱，科学搭配，助力宝宝健康成长。
          </p>

          {categories && (
            <div className="mt-6 flex flex-wrap gap-4 text-sm">
              <div className="bg-white/20 backdrop-blur-sm rounded-xl px-4 py-2">
                🍽️ 食谱总数 <strong>{categories.totalRecipes}</strong>
              </div>
              <div className="bg-white/20 backdrop-blur-sm rounded-xl px-4 py-2">
                📂 分类 <strong>{categories.categories.length}</strong>
              </div>
              <div className="bg-white/20 backdrop-blur-sm rounded-xl px-4 py-2">
                👶 月龄段 <strong>{categories.ageRanges.length}</strong>
              </div>
            </div>
          )}
        </div>
      </header>

      {/* 查询区域 */}
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 mb-8 -mt-6">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4 sm:p-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">
            🔍 查找适合宝宝的辅食
          </h2>
          <div className="flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-[140px]">
              <label className="block text-xs font-medium text-gray-500 mb-1">宝宝月龄</label>
              <select
                value={selectedAge}
                onChange={(e) => setSelectedAge(e.target.value)}
                className="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-300 bg-white"
              >
                <option value="">全部月龄</option>
                <option value="6">6个月（初添辅食）</option>
                <option value="7">7个月</option>
                <option value="8">8个月</option>
                <option value="9">9个月</option>
                <option value="10">10个月</option>
                <option value="11">11个月</option>
                <option value="12">12个月（周岁）</option>
                <option value="18">18个月</option>
                <option value="24">24个月（2岁）</option>
                <option value="30">30个月</option>
                <option value="36">36个月（3岁）</option>
              </select>
            </div>
            <div className="flex-1 min-w-[140px]">
              <label className="block text-xs font-medium text-gray-500 mb-1">食谱分类</label>
              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                className="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-300 bg-white"
              >
                <option value="">全部分类</option>
                <option value="主食">主食</option>
                <option value="蔬菜">蔬菜</option>
                <option value="肉类">肉类</option>
                <option value="汤羹">汤羹</option>
                <option value="点心">点心</option>
                <option value="水果">水果</option>
                <option value="蛋白质">蛋白质</option>
              </select>
            </div>
            <div className="flex-[2] min-w-[200px]">
              <label className="block text-xs font-medium text-gray-500 mb-1">关键词搜索</label>
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="搜索食谱名称、食材、营养..."
                className="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-300"
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleSearch}
                className="px-5 py-2 bg-orange-500 text-white rounded-xl hover:bg-orange-600 transition-colors text-sm font-medium"
              >
                搜索
              </button>
              <button
                onClick={handleRandom}
                className="px-5 py-2 bg-pink-400 text-white rounded-xl hover:bg-pink-500 transition-colors text-sm font-medium"
              >
                🎲 随机推荐
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* 内容区域 */}
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 pb-16">
        {loading ? (
          <div className="flex justify-center py-20">
            <div className="animate-spin h-10 w-10 border-4 border-orange-300 border-t-orange-500 rounded-full" />
          </div>
        ) : showRandom ? (
          <>
            <h2 className="text-xl font-bold text-gray-800 mb-4">🎯 今日推荐食谱</h2>
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {randomRecipes.map((recipe) => (
                <RecipeCard
                  key={recipe.id}
                  recipe={recipe}
                  onViewDetail={() => openDetail(recipe)}
                />
              ))}
            </div>
            <button
              onClick={() => setShowRandom(false)}
              className="mt-6 text-orange-500 hover:text-orange-600 text-sm font-medium"
            >
              ← 返回全部食谱
            </button>
          </>
        ) : (
          <>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-gray-800">📋 食谱列表</h2>
              <span className="text-sm text-gray-400">共 {recipes.length} 道食谱</span>
            </div>
            {recipes.length === 0 ? (
              <div className="text-center py-20 text-gray-400">
                <span className="text-4xl block mb-3">🔍</span>
                没有找到匹配的食谱，试试其他筛选条件
              </div>
            ) : (
              <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {recipes.map((recipe) => (
                  <RecipeCard
                    key={recipe.id}
                    recipe={recipe}
                    onViewDetail={() => openDetail(recipe)}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* 食谱详情 / A2M 支付弹窗 */}
      {(detailRecipe || paymentNeeded) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={closeDetail}>
          <div
            className="bg-white rounded-3xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            {detailRecipe ? (
              <>
                {/* 已解锁 - 完整食谱详情 */}
                <div className="relative p-6 pb-4 border-b border-gray-100">
                  <button
                    onClick={closeDetail}
                    className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-full bg-gray-100 hover:bg-gray-200 text-gray-400 hover:text-gray-600 transition-colors"
                  >
                    ✕
                  </button>
                  <div className="flex items-center gap-3 mb-1">
                    <h3 className="text-xl font-bold text-gray-800">{detailRecipe.name}</h3>
                    <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                      detailRecipe.ageRange.includes('6-8') ? 'bg-green-100 text-green-700' :
                      detailRecipe.ageRange.includes('8-12') ? 'bg-blue-100 text-blue-700' :
                      detailRecipe.ageRange.includes('12-18') ? 'bg-purple-100 text-purple-700' :
                      detailRecipe.ageRange.includes('18-24') ? 'bg-pink-100 text-pink-700' :
                      'bg-orange-100 text-orange-700'
                    }`}>
                      {detailRecipe.ageRange}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-400 mt-1">
                    <span>📂 {detailRecipe.category}</span>
                    <span>⏱ {detailRecipe.cookingTime}分钟</span>
                    <span>● {detailRecipe.difficulty}</span>
                  </div>
                </div>
                <div className="p-6">
                  <div className="mb-4">
                    <h4 className="text-sm font-semibold text-gray-700 mb-2">🥗 营养价值</h4>
                    <p className="text-sm text-gray-600 leading-relaxed bg-green-50 rounded-xl px-4 py-3">
                      {detailRecipe.nutrition}
                    </p>
                  </div>
                  <div className="mb-5">
                    <div className="flex flex-wrap gap-1.5">
                      <span className="text-xs bg-orange-50 text-orange-500 px-2 py-0.5 rounded-full">{detailRecipe.category}</span>
                      {detailRecipe.tags.map((tag) => (
                        <span key={tag} className="text-xs bg-gray-50 text-gray-500 px-2 py-0.5 rounded-full">{tag}</span>
                      ))}
                    </div>
                  </div>
                  <div className="mb-5">
                    <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1">
                      <span>🛒</span> 食材清单
                    </h4>
                    <div className="flex flex-wrap gap-2">
                      {detailRecipe.ingredients.map((ing: string, i: number) => (
                        <span key={i} className="text-sm bg-orange-50 text-gray-700 px-3 py-1.5 rounded-xl border border-orange-100">
                          {ing}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1">
                      <span>👩‍🍳</span> 制作步骤
                    </h4>
                    <ol className="space-y-3">
                      {detailRecipe.steps.map((step: string, i: number) => (
                        <li key={i} className="flex gap-3 text-sm text-gray-600">
                          <span className="w-6 h-6 rounded-full bg-orange-500 text-white text-xs flex items-center justify-center shrink-0 mt-0.5">
                            {i + 1}
                          </span>
                          <span className="leading-relaxed pt-0.5">{step}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                </div>
              </>
            ) : (
              <>
                {/* 需要支付 - A2M 解锁界面 */}
                <div className="relative p-6 pb-4 border-b border-gray-100">
                  <button
                    onClick={closeDetail}
                    className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-full bg-gray-100 hover:bg-gray-200 text-gray-400 hover:text-gray-600 transition-colors"
                  >
                    ✕
                  </button>
                  <div className="flex items-center gap-3 mb-2">
                    <span className="text-2xl">🔒</span>
                    <h3 className="text-xl font-bold text-gray-800">解锁完整食谱</h3>
                  </div>
                  <p className="text-sm text-gray-500">
                    查看完整食材清单和制作步骤需要支付解锁
                  </p>
                </div>
                <div className="p-6">
                  {/* Payment-Needed 信息 */}
                  <div className="mb-5">
                    <h4 className="text-sm font-semibold text-gray-700 mb-2">💳 支付信息</h4>
                    <div className="bg-blue-50 rounded-xl p-4 text-xs text-blue-700 break-all font-mono max-h-32 overflow-y-auto">
                      {paymentNeeded ? (
                        (() => {
                          try {
                            const decoded = JSON.parse(atob(paymentNeeded));
                            return JSON.stringify(decoded, null, 2);
                          } catch {
                            return paymentNeeded;
                          }
                        })()
                      ) : (
                        '正在获取支付信息...'
                      )}
                    </div>
                  </div>

                  {/* Payment-Proof 输入 */}
                  <div className="mb-4">
                    <h4 className="text-sm font-semibold text-gray-700 mb-2">🔑 输入支付凭证</h4>
                    <textarea
                      value={paymentProof}
                      onChange={(e) => setPaymentProof(e.target.value)}
                      placeholder="完成支付后，将支付凭证 (Payment-Proof) 粘贴到此处..."
                      className="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-300 min-h-[80px] font-mono"
                    />
                  </div>

                  {/* 错误提示 */}
                  {unlockError && (
                    <div className="mb-4 bg-red-50 text-red-600 text-sm rounded-xl px-4 py-3">
                      {unlockError}
                    </div>
                  )}

                  {/* 解锁按钮 */}
                  <button
                    onClick={handleUnlock}
                    disabled={unlockLoading || !paymentProof.trim()}
                    className="w-full py-3 rounded-xl text-sm font-bold transition-colors bg-orange-500 text-white hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {unlockLoading ? (
                      <span className="flex items-center justify-center gap-2">
                        <span className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
                        验证中...
                      </span>
                    ) : (
                      '🔓 解锁食谱'
                    )}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="bg-orange-500 text-white py-8">
        <div className="mx-auto max-w-6xl px-4 text-center text-sm text-orange-100">
          <p className="font-medium">宝宝辅食食谱大全 · 陪伴宝宝健康成长</p>
          <p className="mt-1 opacity-75">
            温馨提示：添加新辅食时请逐一尝试，观察宝宝有无过敏反应
          </p>
        </div>
      </footer>
    </div>
  );
}

/** 食谱卡片组件 */
function RecipeCard({
  recipe,
  onViewDetail,
}: {
  recipe: RecipePreview;
  onViewDetail: () => void;
}) {
  const getAgeBadgeColor = (range: string) => {
    if (range.includes('6-8')) return 'bg-green-100 text-green-700';
    if (range.includes('8-12')) return 'bg-blue-100 text-blue-700';
    if (range.includes('12-18')) return 'bg-purple-100 text-purple-700';
    if (range.includes('18-24')) return 'bg-pink-100 text-pink-700';
    return 'bg-orange-100 text-orange-700';
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm hover:shadow-md transition-shadow border border-gray-100 overflow-hidden group">
      <div className="p-5">
        {/* Header */}
        <div className="flex items-start justify-between mb-2">
          <h3 className="font-bold text-gray-800 text-lg leading-tight group-hover:text-orange-500 transition-colors">
            {recipe.name}
          </h3>
          <div className="flex items-center gap-1.5 shrink-0">
            {recipe.locked && (
              <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">🔒</span>
            )}
            <span className={`text-xs px-2 py-1 rounded-full font-medium ${getAgeBadgeColor(recipe.ageRange)}`}>
              {recipe.ageRange}
            </span>
          </div>
        </div>

        {/* Tags */}
        <div className="flex flex-wrap gap-1.5 mb-3">
          <span className="text-xs bg-orange-50 text-orange-500 px-2 py-0.5 rounded-full">
            {recipe.category}
          </span>
          {recipe.tags.slice(0, 3).map((tag) => (
            <span key={tag} className="text-xs bg-gray-50 text-gray-500 px-2 py-0.5 rounded-full">
              {tag}
            </span>
          ))}
          {recipe.tags.length > 3 && (
            <span className="text-xs text-gray-300">+{recipe.tags.length - 3}</span>
          )}
        </div>

        {/* Info */}
        <div className="flex items-center gap-3 text-xs text-gray-400 mb-3">
          <span>⏱ {recipe.cookingTime}分钟</span>
          <span className={recipe.difficulty === '简单' ? 'text-green-500' : recipe.difficulty === '中等' ? 'text-yellow-500' : 'text-red-500'}>
            ● {recipe.difficulty}
          </span>
        </div>

        {/* Nutrition preview */}
        <p className="text-xs text-gray-400 line-clamp-2 mb-3">{recipe.nutrition}</p>

        {/* View button */}
        <button
          onClick={onViewDetail}
          className="w-full py-2 rounded-xl text-sm font-medium transition-colors bg-orange-50 text-orange-500 hover:bg-orange-100"
        >
          {recipe.locked ? '🔒 支付解锁食谱' : '👩‍🍳 查看完整食谱'}
        </button>
      </div>
    </div>
  );
}
