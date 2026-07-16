import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Plus, Edit, Trash2, Search, Filter, ArrowUpDown, Loader2, Package, History } from 'lucide-react';
import { apiFetch } from '../utils/api.js';
import { Product } from '../types.js';
import InventoryAdjustmentModal from '../components/InventoryAdjustmentModal.js';

export default function Products() {
  const [products, setProducts] = useState<Product[]>([]);
  const [totalProducts, setTotalProducts] = useState(0);
  const [page, setPage] = useState(1);
  const limit = 50;

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isAdjustmentModalOpen, setIsAdjustmentModalOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [adjustingProduct, setAdjustingProduct] = useState<Product | null>(null);
  
  // Search, Filter, Sort state
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('All');
  const [sortBy, setSortBy] = useState('name_asc');
  
  // Delete confirmation state
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const [formData, setFormData] = useState({
    code: '',
    name: '',
    category: 'Fertilizer',
    unit: 'Bag',
    price_ex_gst: '',
    gst_rate: '5',
    hsn_code: '',
    stock: '0'
  });

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchProducts();
    }, 300); // Debounce fetch on search
    return () => clearTimeout(timer);
  }, [page, limit, searchQuery, categoryFilter, sortBy]);

  const fetchProducts = async () => {
    const params = new URLSearchParams({
      page: page.toString(),
      limit: limit.toString(),
      search: searchQuery,
      category: categoryFilter,
      sort: sortBy
    });
    const res = await apiFetch(`/api/products?${params}`);
    const data = await res.json();
    if (data.data) {
      setProducts(data.data);
      setTotalProducts(data.total);
    } else {
      // Fallback if data is array (e.g. some tests mock returning array)
      setProducts(Array.isArray(data) ? data : []);
      setTotalProducts(Array.isArray(data) ? data.length : 0);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const url = editingProduct ? `/api/products/${editingProduct.id}` : '/api/products';
    const method = editingProduct ? 'PUT' : 'POST';
    
    try {
      const payload = {
        ...formData,
        price_ex_gst: parseFloat(formData.price_ex_gst),
        gst_rate: parseFloat(formData.gst_rate),
        stock: parseFloat(formData.stock)
      };

      const res = await apiFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (!res.ok) {
        const errorData = await res.json();
        alert(`Error: ${errorData.error || 'Failed to save product'}`);
        return;
      }
      
      setIsModalOpen(false);
      setEditingProduct(null);
      fetchProducts();
    } catch (err) {
      console.error(err);
      alert('An error occurred while saving the product.');
    }
  };

  const confirmDelete = async () => {
    if (deleteConfirmId !== null) {
      setIsDeleting(true);
      try {
        await apiFetch(`/api/products/${deleteConfirmId}`, { method: 'DELETE' });
        setDeleteConfirmId(null);
        fetchProducts();
      } finally {
        setIsDeleting(false);
      }
    }
  };

  const openEditModal = useCallback((product: Product) => {
    setEditingProduct(product);
    setFormData({
      code: product.code,
      name: product.name,
      category: product.category,
      unit: product.unit,
      price_ex_gst: product.price_ex_gst.toString(),
      gst_rate: product.gst_rate.toString(),
      hsn_code: product.hsn_code,
      stock: product.stock?.toString() || '0'
    });
    setIsModalOpen(true);
  }, []);

  // ⚡ Bolt: Memoize the 50 table rows to prevent re-rendering them on every single keystroke in the search input
  const renderedProducts = useMemo(() => {
    return products.map((product: Product) => (
      <tr key={product.id} className="hover:bg-zinc-800/50 transition-colors">
        <td className="px-6 py-4 whitespace-nowrap text-sm font-bold text-white">{product.code}</td>
        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-zinc-300">{product.name}</td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-zinc-400">
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-zinc-800 text-zinc-300 border border-zinc-700">
            {product.category}
          </span>
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-zinc-500">{product.hsn_code}</td>
        <td className="px-6 py-4 whitespace-nowrap text-sm font-bold text-lime-400 text-right">₹{product.price_ex_gst.toFixed(2)}</td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-zinc-400 text-right">{product.gst_rate}%</td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-right font-bold">
          <span className={product.stock <= 10 ? 'text-rose-500' : 'text-zinc-300'}>
            {product.stock} {product.unit}
          </span>
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
          <button 
            onClick={() => {
              setAdjustingProduct(product);
              setIsAdjustmentModalOpen(true);
            }} 
            className="text-amber-400 hover:text-amber-300 mr-4 transition-colors" 
            aria-label={`Inventory History ${product.name}`} 
            title="Stock adjustment & history"
          >
            <History className="h-5 w-5" />
          </button>
          <button onClick={() => openEditModal(product)} className="text-cyan-400 hover:text-cyan-300 mr-4 transition-colors" aria-label={`Edit ${product.name}`} title="Edit product">
            <Edit className="h-5 w-5" />
          </button>
          <button onClick={() => setDeleteConfirmId(product.id)} className="text-rose-500 hover:text-rose-400 transition-colors" aria-label={`Delete ${product.name}`} title="Delete product">
            <Trash2 className="h-5 w-5" />
          </button>
        </td>
      </tr>
    ));
  }, [products, openEditModal, setDeleteConfirmId]);

  const totalPages = Math.ceil(totalProducts / limit);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-black tracking-tight text-white">Products Master</h1>
        <button
          onClick={() => {
            setEditingProduct(null);
            setFormData({ code: '', name: '', category: 'Fertilizer', unit: 'Bag', price_ex_gst: '', gst_rate: '5', hsn_code: '', stock: '0' });
            setIsModalOpen(true);
          }}
          className="inline-flex items-center px-6 py-3 border-2 border-zinc-950 text-sm font-bold rounded-xl shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] text-zinc-950 bg-lime-400 hover:bg-lime-300 hover:translate-y-[-2px] hover:translate-x-[-2px] hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] transition-all"
        >
          <Plus className="-ml-1 mr-2 h-5 w-5" />
          Add Product
        </button>
      </div>

      {/* Filters and Search */}
      <div className="bg-zinc-900 border-2 border-zinc-800 rounded-2xl p-4 flex flex-col sm:flex-row gap-4 justify-between items-center">
        <div className="relative w-full sm:w-1/3">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Search className="h-5 w-5 text-zinc-500" />
          </div>
          <input
            type="text"
            aria-label="Search products"
            placeholder="Search by Code or Name..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            className="block w-full pl-10 sm:text-sm"
          />
        </div>
        
        <div className="flex gap-4 w-full sm:w-auto">
          <div className="flex items-center">
            <Filter className="h-5 w-5 text-zinc-500 mr-2" />
            <select
              value={categoryFilter}
              onChange={(e) => {
                setCategoryFilter(e.target.value);
                setPage(1);
              }}
              className="block w-full sm:text-sm"
              aria-label="Filter by category"
            >
              <option value="All">All Categories</option>
              <option value="Fertilizer">Fertilizer</option>
              <option value="Pesticide">Pesticide</option>
              <option value="Seed">Seed</option>
              <option value="Herbicide">Herbicide</option>
              <option value="Micronutrient">Micronutrient</option>
            </select>
          </div>
          
          <div className="flex items-center">
            <ArrowUpDown className="h-5 w-5 text-zinc-500 mr-2" />
            <select
              value={sortBy}
              onChange={(e) => {
                setSortBy(e.target.value);
                setPage(1);
              }}
              className="block w-full sm:text-sm"
              aria-label="Sort products"
            >
              <option value="name_asc">Name (A-Z)</option>
              <option value="name_desc">Name (Z-A)</option>
              <option value="price_asc">Price (Low to High)</option>
              <option value="price_desc">Price (High to Low)</option>
            </select>
          </div>
        </div>
      </div>

      <div className="bg-zinc-900 border-2 border-zinc-800 overflow-hidden rounded-2xl">
        <table className="min-w-full divide-y divide-zinc-800">
          <thead className="bg-zinc-950/50">
            <tr>
              <th className="px-6 py-4 text-left text-xs font-bold text-zinc-400 uppercase tracking-wider">Code</th>
              <th className="px-6 py-4 text-left text-xs font-bold text-zinc-400 uppercase tracking-wider">Name</th>
              <th className="px-6 py-4 text-left text-xs font-bold text-zinc-400 uppercase tracking-wider">Category</th>
              <th className="px-6 py-4 text-left text-xs font-bold text-zinc-400 uppercase tracking-wider">HSN</th>
              <th className="px-6 py-4 text-right text-xs font-bold text-zinc-400 uppercase tracking-wider">Price (ex GST)</th>
              <th className="px-6 py-4 text-right text-xs font-bold text-zinc-400 uppercase tracking-wider">GST %</th>
              <th className="px-6 py-4 text-right text-xs font-bold text-zinc-400 uppercase tracking-wider">Stock</th>
              <th className="px-6 py-4 text-right text-xs font-bold text-zinc-400 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-zinc-900 divide-y divide-zinc-800">
            {products.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-6 py-16 text-center">
                  <div className="flex flex-col items-center justify-center">
                    {(searchQuery !== '' || categoryFilter !== 'All') ? (
                      <>
                        <div className="bg-zinc-800/50 p-4 rounded-full mb-4">
                          <Search className="h-8 w-8 text-zinc-500" />
                        </div>
                        <h3 className="text-lg font-bold text-white mb-2">No matching products</h3>
                        <p className="text-zinc-400 text-sm mb-6 max-w-sm mx-auto">
                          We couldn't find any products matching your current search and filter criteria.
                        </p>
                        <button
                          onClick={() => {
                            setSearchQuery('');
                            setCategoryFilter('All');
                          }}
                          className="inline-flex items-center px-4 py-2 border-2 border-zinc-800 text-sm font-bold rounded-xl text-zinc-300 bg-zinc-950 hover:bg-zinc-800 transition-colors"
                        >
                          Clear Filters
                        </button>
                      </>
                    ) : (
                      <>
                        <div className="bg-zinc-800/50 p-4 rounded-full mb-4">
                          <Package className="h-8 w-8 text-zinc-500" />
                        </div>
                        <h3 className="text-lg font-bold text-white mb-2">No products yet</h3>
                        <p className="text-zinc-400 text-sm mb-6 max-w-sm mx-auto">
                          Get started by adding your first product to the inventory.
                        </p>
                        <button
                          onClick={() => {
                            setEditingProduct(null);
                            setFormData({ code: '', name: '', category: 'Fertilizer', unit: 'Bag', price_ex_gst: '', gst_rate: '5', hsn_code: '', stock: '0' });
                            setIsModalOpen(true);
                          }}
                          className="inline-flex items-center px-4 py-2 border-2 border-zinc-950 text-sm font-bold rounded-xl shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] text-zinc-950 bg-lime-400 hover:bg-lime-300 hover:translate-y-[-2px] hover:translate-x-[-2px] hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] transition-all"
                        >
                          <Plus className="-ml-1 mr-2 h-4 w-4" />
                          Add Product
                        </button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ) : (
              renderedProducts
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between bg-zinc-900 border-2 border-zinc-800 px-4 py-3 sm:px-6 rounded-2xl">
          <div className="flex-1 flex justify-between sm:hidden">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="relative inline-flex items-center px-4 py-2 border-2 border-zinc-800 text-sm font-medium rounded-xl text-zinc-300 bg-zinc-950 hover:bg-zinc-800 disabled:opacity-50"
            >
              Previous
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="ml-3 relative inline-flex items-center px-4 py-2 border-2 border-zinc-800 text-sm font-medium rounded-xl text-zinc-300 bg-zinc-950 hover:bg-zinc-800 disabled:opacity-50"
            >
              Next
            </button>
          </div>
          <div className="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
            <div>
              <p className="text-sm text-zinc-400">
                Showing <span className="font-medium text-white">{((page - 1) * limit) + 1}</span> to <span className="font-medium text-white">{Math.min(page * limit, totalProducts)}</span> of <span className="font-medium text-white">{totalProducts}</span> results
              </p>
            </div>
            <div>
              <nav className="relative z-0 inline-flex rounded-xl shadow-sm -space-x-px" aria-label="Pagination">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="relative inline-flex items-center px-2 py-2 rounded-l-xl border-2 border-zinc-800 bg-zinc-950 text-sm font-medium text-zinc-400 hover:bg-zinc-800 disabled:opacity-50"
                >
                  <span className="sr-only">Previous</span>
                  &larr;
                </button>
                <span className="relative inline-flex items-center px-4 py-2 border-y-2 border-zinc-800 bg-zinc-900 text-sm font-medium text-white">
                  Page {page} of {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="relative inline-flex items-center px-2 py-2 rounded-r-xl border-2 border-zinc-800 bg-zinc-950 text-sm font-medium text-zinc-400 hover:bg-zinc-800 disabled:opacity-50"
                >
                  <span className="sr-only">Next</span>
                  &rarr;
                </button>
              </nav>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirmId !== null && (
        <div className="fixed inset-0 z-60 overflow-y-auto">
          <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
            <div className="fixed inset-0 transition-opacity z-0" aria-hidden="true" onClick={() => setDeleteConfirmId(null)}>
              <div className="absolute inset-0 bg-zinc-950 opacity-75 backdrop-blur-sm"></div>
            </div>
            <span className="hidden sm:inline-block sm:align-middle sm:h-screen" aria-hidden="true">&#8203;</span>
            <div className="relative z-10 inline-block align-bottom bg-zinc-900 border-2 border-zinc-800 rounded-2xl text-left overflow-hidden shadow-2xl transform transition-all sm:my-8 sm:align-middle sm:max-w-lg sm:w-full">
              <div className="bg-zinc-900 px-4 pt-5 pb-4 sm:p-6 sm:pb-4">
                <div className="sm:flex sm:items-start">
                  <div className="mx-auto shrink-0 flex items-center justify-center h-12 w-12 rounded-full bg-rose-500/10 sm:mx-0 sm:h-10 sm:w-10">
                    <Trash2 className="h-6 w-6 text-rose-500" aria-hidden="true" />
                  </div>
                  <div className="mt-3 text-center sm:mt-0 sm:ml-4 sm:text-left">
                    <h3 className="text-xl font-bold text-white">Delete Product</h3>
                    <div className="mt-2">
                      <p className="text-sm text-zinc-400">
                        Are you sure you want to delete this product? This action cannot be undone.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
              <div className="bg-zinc-950/50 px-4 py-4 sm:px-6 sm:flex sm:flex-row-reverse border-t border-zinc-800">
                <button type="button" disabled={isDeleting} onClick={confirmDelete} className="w-full inline-flex items-center justify-center rounded-xl border-2 border-zinc-950 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] px-4 py-2 bg-rose-500 text-base font-bold text-zinc-950 hover:bg-rose-400 hover:translate-y-[-2px] hover:translate-x-[-2px] hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] transition-all sm:ml-3 sm:w-auto sm:text-sm disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:hover:translate-x-0 disabled:hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
                  {isDeleting && <Loader2 className="animate-spin -ml-1 mr-2 h-4 w-4" />}
                  {isDeleting ? 'Deleting...' : 'Delete'}
                </button>
                <button type="button" disabled={isDeleting} onClick={() => setDeleteConfirmId(null)} className="mt-3 w-full inline-flex justify-center rounded-xl border-2 border-zinc-700 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] px-4 py-2 bg-zinc-800 text-base font-bold text-white hover:bg-zinc-700 hover:translate-y-[-2px] hover:translate-x-[-2px] hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] transition-all sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:hover:translate-x-0 disabled:hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add/Edit Product Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-60 overflow-y-auto">
          <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
            <div className="fixed inset-0 transition-opacity z-0" aria-hidden="true" onClick={() => setIsModalOpen(false)}>
              <div className="absolute inset-0 bg-zinc-950 opacity-75 backdrop-blur-sm"></div>
            </div>
            <span className="hidden sm:inline-block sm:align-middle sm:h-screen" aria-hidden="true">&#8203;</span>
            <div className="relative z-10 inline-block align-bottom bg-zinc-900 border-2 border-zinc-800 rounded-2xl text-left overflow-hidden shadow-2xl transform transition-all sm:my-8 sm:align-middle sm:max-w-2xl sm:w-full">
              <form onSubmit={handleSubmit}>
                <div className="bg-zinc-900 px-4 pt-5 pb-4 sm:p-6 sm:pb-4">
                  <h3 className="text-2xl font-black text-white mb-6">
                    {editingProduct ? 'Edit Product' : 'Add New Product'}
                  </h3>
                  <div className="grid grid-cols-2 gap-6">
                    <div>
                      <label htmlFor="product-code" className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">Code/SKU</label>
                      <input id="product-code" type="text" required value={formData.code} onChange={e => setFormData({...formData, code: e.target.value})} disabled={isSaving} className="block w-full sm:text-sm bg-zinc-950 border-2 border-zinc-800 rounded-lg p-2 text-white focus:ring-lime-400 focus:border-lime-400 outline-none disabled:opacity-50 disabled:cursor-not-allowed" />
                    </div>
                    <div>
                      <label htmlFor="product-hsn" className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">HSN Code</label>
                      <input id="product-hsn" type="text" required value={formData.hsn_code} onChange={e => setFormData({...formData, hsn_code: e.target.value})} disabled={isSaving} className="block w-full sm:text-sm bg-zinc-950 border-2 border-zinc-800 rounded-lg p-2 text-white focus:ring-lime-400 focus:border-lime-400 outline-none disabled:opacity-50 disabled:cursor-not-allowed" />
                    </div>
                    <div className="col-span-2">
                      <label htmlFor="product-name" className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">Name</label>
                      <input id="product-name" type="text" required value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} disabled={isSaving} className="block w-full sm:text-sm bg-zinc-950 border-2 border-zinc-800 rounded-lg p-2 text-white focus:ring-lime-400 focus:border-lime-400 outline-none disabled:opacity-50 disabled:cursor-not-allowed" />
                    </div>
                    <div>
                      <label htmlFor="product-category" className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">Category</label>
                      <select id="product-category" value={formData.category} onChange={e => setFormData({...formData, category: e.target.value})} disabled={isSaving} className="block w-full sm:text-sm bg-zinc-950 border-2 border-zinc-800 rounded-lg p-2 text-white focus:ring-lime-400 focus:border-lime-400 outline-none disabled:opacity-50 disabled:cursor-not-allowed">
                        <option>Fertilizer</option>
                        <option>Pesticide</option>
                        <option>Seed</option>
                        <option>Herbicide</option>
                        <option>Micronutrient</option>
                      </select>
                    </div>
                    <div>
                      <label htmlFor="product-unit" className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">Unit</label>
                      <select id="product-unit" value={formData.unit} onChange={e => setFormData({...formData, unit: e.target.value})} disabled={isSaving} className="block w-full sm:text-sm bg-zinc-950 border-2 border-zinc-800 rounded-lg p-2 text-white focus:ring-lime-400 focus:border-lime-400 outline-none disabled:opacity-50 disabled:cursor-not-allowed">
                        <option>Bag</option>
                        <option>Kg</option>
                        <option>Litre</option>
                        <option>Packet</option>
                        <option>Bottle</option>
                      </select>
                    </div>
                    <div>
                      <label htmlFor="product-price" className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">Price (ex GST)</label>
                      <input id="product-price" type="number" step="0.01" required value={formData.price_ex_gst} onChange={e => setFormData({...formData, price_ex_gst: e.target.value})} disabled={isSaving} className="block w-full sm:text-sm bg-zinc-950 border-2 border-zinc-800 rounded-lg p-2 text-white focus:ring-lime-400 focus:border-lime-400 outline-none disabled:opacity-50 disabled:cursor-not-allowed" />
                    </div>
                    <div>
                      <label htmlFor="product-gst" className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">GST Rate (%)</label>
                      <select id="product-gst" value={formData.gst_rate} onChange={e => setFormData({...formData, gst_rate: e.target.value})} disabled={isSaving} className="block w-full sm:text-sm bg-zinc-950 border-2 border-zinc-800 rounded-lg p-2 text-white focus:ring-lime-400 focus:border-lime-400 outline-none disabled:opacity-50 disabled:cursor-not-allowed">
                        <option value="0">0%</option>
                        <option value="5">5%</option>
                        <option value="12">12%</option>
                        <option value="18">18%</option>
                        <option value="28">28%</option>
                      </select>
                    </div>
                    <div>
                      <label htmlFor="product-stock" className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">Stock Quantity</label>
                      <input id="product-stock" type="number" step="0.01" required value={formData.stock} onChange={e => setFormData({...formData, stock: e.target.value})} disabled={isSaving} className="block w-full sm:text-sm bg-zinc-950 border-2 border-zinc-800 rounded-lg p-2 text-white focus:ring-lime-400 focus:border-lime-400 outline-none disabled:opacity-50 disabled:cursor-not-allowed" />
                    </div>
                  </div>
                </div>
                <div className="bg-zinc-950/50 px-4 py-4 sm:px-6 sm:flex sm:flex-row-reverse border-t border-zinc-800">
                  <button type="submit" disabled={isSaving} className="w-full inline-flex items-center justify-center rounded-xl border-2 border-zinc-950 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] px-6 py-2 bg-lime-400 text-base font-bold text-zinc-950 hover:bg-lime-300 hover:translate-y-[-2px] hover:translate-x-[-2px] hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] transition-all sm:ml-3 sm:w-auto sm:text-sm disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:hover:translate-x-0 disabled:hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
                    {isSaving && <Loader2 className="animate-spin -ml-1 mr-2 h-4 w-4" />}
                    {isSaving ? 'Saving...' : 'Save'}
                  </button>
                  <button type="button" disabled={isSaving} onClick={() => setIsModalOpen(false)} className="mt-3 w-full inline-flex justify-center rounded-xl border-2 border-zinc-700 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] px-6 py-2 bg-zinc-800 text-base font-bold text-white hover:bg-zinc-700 hover:translate-y-[-2px] hover:translate-x-[-2px] hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] transition-all sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:hover:translate-x-0 disabled:hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Inventory Adjustment Modal */}
      {isAdjustmentModalOpen && adjustingProduct && (
        <InventoryAdjustmentModal
          product={adjustingProduct}
          onClose={() => {
            setIsAdjustmentModalOpen(false);
            setAdjustingProduct(null);
          }}
          onSuccess={fetchProducts}
        />
      )}
    </div>
  );
}
