import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Trash2, Loader2 } from 'lucide-react';
import { apiFetch } from '../utils/api';
import { Product } from '../types';

interface BillItem {
  product_id: number;
  product_name: string;
  product_code: string;
  hsn_code: string;
  unit: string;
  quantity: number;
  price_ex_gst: number;
  gst_rate: number;
  cgst_amount: number;
  sgst_amount: number;
  igst_amount: number;
  total: number;
}

export default function NewBill() {
  const navigate = useNavigate();
  const [billType, setBillType] = useState('cash');
  const [searchQuery, setSearchQuery] = useState('');
  const [filteredProducts, setFilteredProducts] = useState<Product[]>([]);
  
  const [customer, setCustomer] = useState({
    name: '',
    mobile: '',
    address: '',
    gstin: '',
    state: ''
  });

  const [isInterState, setIsInterState] = useState(false);
  const [items, setItems] = useState<BillItem[]>([]);
  const [discount, setDiscount] = useState(0);
  const [discountType, setDiscountType] = useState<'value' | 'percentage'>('value');
  const [amountPaid, setAmountPaid] = useState<string>('');
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (searchQuery.length > 1) {
      const timer = setTimeout(() => {
        apiFetch(`/api/products?search=${encodeURIComponent(searchQuery)}&limit=10`)
          .then(res => res.json())
          .then(data => {
            setFilteredProducts(data.data || (Array.isArray(data) ? data : []));
          })
          .catch(err => console.error('Failed to fetch products:', err));
      }, 300);
      return () => clearTimeout(timer);
    } else {
      setFilteredProducts([]);
    }
  }, [searchQuery]);

  const addItem = (product: Product) => {
    const existing = items.find(i => i.product_id === product.id);
    if (existing) {
      updateQuantity(product.id, existing.quantity + 1);
    } else {
      const price = product.price_ex_gst;
      const gstRate = product.gst_rate;
      const quantity = 1;
      const taxableValue = price * quantity;
      const cgst = isInterState ? 0 : (taxableValue * (gstRate / 2)) / 100;
      const sgst = isInterState ? 0 : (taxableValue * (gstRate / 2)) / 100;
      const igst = isInterState ? (taxableValue * gstRate) / 100 : 0;
      const gstAmount = cgst + sgst + igst;
      
      setItems([...items, {
        product_id: product.id,
        product_name: product.name,
        product_code: product.code,
        hsn_code: product.hsn_code,
        unit: product.unit,
        quantity: quantity,
        price_ex_gst: price,
        gst_rate: gstRate,
        cgst_amount: cgst,
        sgst_amount: sgst,
        igst_amount: igst,
        total: taxableValue + gstAmount
      }]);
    }
    setSearchQuery('');
  };

  const updateQuantity = (productId: number, qty: number) => {
    if (qty <= 0) return;
    setItems(items.map(item => {
      if (item.product_id === productId) {
        const taxableValue = item.price_ex_gst * qty;
        const cgst = isInterState ? 0 : (taxableValue * (item.gst_rate / 2)) / 100;
        const sgst = isInterState ? 0 : (taxableValue * (item.gst_rate / 2)) / 100;
        const igst = isInterState ? (taxableValue * item.gst_rate) / 100 : 0;
        const gstAmount = cgst + sgst + igst;
        return {
          ...item,
          quantity: qty,
          cgst_amount: cgst,
          sgst_amount: sgst,
          igst_amount: igst,
          total: taxableValue + gstAmount
        };
      }
      return item;
    }));
  };

  const removeItem = (productId: number) => {
    setItems(items.filter(i => i.product_id !== productId));
  };

  // Recalculate items when isInterState changes
  useEffect(() => {
    setItems(currentItems => currentItems.map(item => {
      const taxableValue = item.price_ex_gst * item.quantity;
      const cgst = isInterState ? 0 : (taxableValue * (item.gst_rate / 2)) / 100;
      const sgst = isInterState ? 0 : (taxableValue * (item.gst_rate / 2)) / 100;
      const igst = isInterState ? (taxableValue * item.gst_rate) / 100 : 0;
      const gstAmount = cgst + sgst + igst;
      return {
        ...item,
        cgst_amount: cgst,
        sgst_amount: sgst,
        igst_amount: igst,
        total: taxableValue + gstAmount
      };
    }));
  }, [isInterState]);

  const subtotal = items.reduce((sum, item) => sum + (item.price_ex_gst * item.quantity), 0);
  const totalCgst = items.reduce((sum, item) => sum + item.cgst_amount, 0);
  const totalSgst = items.reduce((sum, item) => sum + item.sgst_amount, 0);
  const totalIgst = items.reduce((sum, item) => sum + (item.igst_amount || 0), 0);
  
  const totalBeforeDiscount = subtotal + totalCgst + totalSgst + totalIgst;
  const calculatedDiscount = discountType === 'percentage' 
    ? (totalBeforeDiscount * discount) / 100 
    : discount;
  const grandTotal = totalBeforeDiscount - calculatedDiscount;

  const handleSave = async () => {
    if (items.length === 0) {
      alert('Please add at least one item to the bill.');
      return;
    }
    if (billType === 'b2b' && (!customer.name || !customer.gstin)) {
      alert('Name and GSTIN are required for B2B sales.');
      return;
    }

    const payload = {
      type: billType,
      customer_name: customer.name,
      customer_mobile: customer.mobile,
      customer_address: customer.address,
      customer_gstin: customer.gstin,
      customer_state: customer.state,
      subtotal,
      discount: calculatedDiscount,
      cgst_total: totalCgst,
      sgst_total: totalSgst,
      igst_total: totalIgst,
      grand_total: grandTotal,
      amount_paid: amountPaid === '' ? grandTotal : parseFloat(amountPaid),
      payment_status: amountPaid === '' || parseFloat(amountPaid) >= grandTotal ? 'Paid' : parseFloat(amountPaid) > 0 ? 'Partial' : 'Unpaid',
      items
    };

    try {
      setIsSaving(true);
      const res = await apiFetch('/api/invoices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.success) {
        navigate('/invoices');
      } else {
        alert(data.error);
      }
    } catch (err) {
      console.error(err);
      alert('Failed to save invoice');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-black tracking-tight text-white">Create New Bill</h1>
        <div className="flex space-x-6 bg-zinc-900 border-2 border-zinc-800 p-2 rounded-xl">
          <label className="inline-flex items-center cursor-pointer">
            <input type="radio" className="form-radio text-lime-400 focus:ring-lime-400 bg-zinc-950 border-zinc-800 w-5 h-5" name="billType" value="cash" checked={billType === 'cash'} onChange={(e) => setBillType(e.target.value)} />
            <span className="ml-3 font-bold text-zinc-300">Cash Sale</span>
          </label>
          <label className="inline-flex items-center cursor-pointer">
            <input type="radio" className="form-radio text-lime-400 focus:ring-lime-400 bg-zinc-950 border-zinc-800 w-5 h-5" name="billType" value="b2b" checked={billType === 'b2b'} onChange={(e) => setBillType(e.target.value)} />
            <span className="ml-3 font-bold text-zinc-300">B2B Sale</span>
          </label>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Customer & Search */}
        <div className="space-y-6 lg:col-span-1">
          <div className="bg-zinc-900 border-2 border-zinc-800 rounded-2xl p-6">
            <h2 className="text-xl font-black text-white mb-6 uppercase tracking-wider">Customer Details</h2>
            <div className="space-y-5">
              <div>
                <label className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">Name {billType === 'b2b' && <span className="text-rose-500">*</span>}</label>
                <input type="text" value={customer.name} onChange={e => setCustomer({...customer, name: e.target.value})} className="block w-full sm:text-sm" />
              </div>
              <div>
                <label className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">Mobile</label>
                <input 
                  type="text" 
                  value={customer.mobile} 
                  onChange={e => {
                    const val = e.target.value.replace(/\D/g, '').slice(0, 10);
                    setCustomer({...customer, mobile: val});
                  }} 
                  className="block w-full sm:text-sm" 
                  placeholder="10-digit mobile number"
                />
              </div>
              {billType === 'b2b' && (
                <>
                  <div>
                    <label className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">GSTIN <span className="text-rose-500">*</span></label>
                    <input type="text" value={customer.gstin} onChange={e => setCustomer({...customer, gstin: e.target.value})} className="block w-full sm:text-sm" />
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">Address</label>
                    <textarea value={customer.address} onChange={e => setCustomer({...customer, address: e.target.value})} rows={2} className="block w-full sm:text-sm" />
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">State</label>
                    <input type="text" value={customer.state} onChange={e => setCustomer({...customer, state: e.target.value})} className="block w-full sm:text-sm" placeholder="e.g. Maharashtra" />
                  </div>
                </>
              )}
              <div className="pt-2">
                <label className="inline-flex items-center cursor-pointer">
                  <input type="checkbox" className="form-checkbox text-lime-400 focus:ring-lime-400 bg-zinc-950 border-zinc-800 w-5 h-5 rounded" checked={isInterState} onChange={(e) => setIsInterState(e.target.checked)} />
                  <span className="ml-3 font-bold text-zinc-300">Inter-state Sale (Apply IGST)</span>
                </label>
              </div>
            </div>
          </div>

          <div className="bg-zinc-900 border-2 border-zinc-800 rounded-2xl p-6 relative z-50">
            <h2 className="text-xl font-black text-white mb-6 uppercase tracking-wider">Add Product</h2>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Search className="h-5 w-5 text-zinc-500" />
              </div>
              <input
                type="text"
                aria-label="Search products to add"
                placeholder="Search by name or code..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="block w-full pl-10 sm:text-sm"
              />
            </div>
            {filteredProducts.length > 0 && (
              <ul className="absolute z-50 mt-2 w-[calc(100%-3rem)] bg-zinc-800 border-2 border-zinc-700 shadow-2xl max-h-60 rounded-xl py-2 text-base overflow-auto focus:outline-none sm:text-sm">
                {filteredProducts.map((product) => (
                  <li
                    key={product.id}
                    onClick={() => addItem(product)}
                    className="cursor-pointer select-none relative py-3 px-4 hover:bg-zinc-700 transition-colors border-b border-zinc-700/50 last:border-0"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-bold text-white truncate">{product.name}</span>
                      <span className="text-lime-400 font-bold text-sm">₹{product.price_ex_gst}</span>
                    </div>
                    <span className="text-zinc-400 font-medium text-xs bg-zinc-900 px-2 py-1 rounded-md">{product.code} | {product.category}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Right Column: Bill Items & Summary */}
        <div className="bg-zinc-900 border-2 border-zinc-800 rounded-2xl lg:col-span-2 flex flex-col h-[calc(100vh-8rem)]">
          <div className="p-6 border-b-2 border-zinc-800">
            <h2 className="text-xl font-black text-white uppercase tracking-wider">Bill Items</h2>
          </div>
          <div className="flex-1 overflow-auto p-6">
            {items.length === 0 ? (
              <div className="text-center text-zinc-500 py-20 font-bold text-lg border-2 border-dashed border-zinc-800 rounded-xl">No items added yet.</div>
            ) : (
              <div className="border-2 border-zinc-800 rounded-xl overflow-hidden">
                <table className="min-w-full divide-y divide-zinc-800">
                  <thead className="bg-zinc-950/50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-bold text-zinc-400 uppercase tracking-wider">Item</th>
                      <th className="px-4 py-3 text-right text-xs font-bold text-zinc-400 uppercase tracking-wider">Rate</th>
                      <th className="px-4 py-3 text-center text-xs font-bold text-zinc-400 uppercase tracking-wider">Qty</th>
                      <th className="px-4 py-3 text-right text-xs font-bold text-zinc-400 uppercase tracking-wider">Taxable</th>
                      {!isInterState ? (
                        <>
                          <th className="px-4 py-3 text-right text-xs font-bold text-zinc-400 uppercase tracking-wider">CGST</th>
                          <th className="px-4 py-3 text-right text-xs font-bold text-zinc-400 uppercase tracking-wider">SGST</th>
                        </>
                      ) : (
                        <th className="px-4 py-3 text-right text-xs font-bold text-zinc-400 uppercase tracking-wider">IGST</th>
                      )}
                      <th className="px-4 py-3 text-right text-xs font-bold text-zinc-400 uppercase tracking-wider">Total</th>
                      <th className="px-4 py-3"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800 bg-zinc-900">
                    {items.map((item) => (
                      <tr key={item.product_id} className="hover:bg-zinc-800/50 transition-colors">
                        <td className="px-4 py-4 text-sm text-white">
                          <div className="font-bold">{item.product_name}</div>
                          <div className="text-xs font-mono text-zinc-500 mt-1">HSN: {item.hsn_code}</div>
                        </td>
                        <td className="px-4 py-4 text-sm font-bold text-zinc-400 text-right">₹{item.price_ex_gst.toFixed(2)}</td>
                        <td className="px-4 py-4 text-sm text-center">
                          <input
                            type="number"
                            min="1"
                            value={item.quantity}
                            onChange={(e) => updateQuantity(item.product_id, parseFloat(e.target.value) || 1)}
                            className="w-20 text-center sm:text-sm font-bold"
                          />
                        </td>
                        <td className="px-4 py-4 text-sm font-bold text-zinc-400 text-right">₹{(item.price_ex_gst * item.quantity).toFixed(2)}</td>
                        {!isInterState ? (
                          <>
                            <td className="px-4 py-4 text-sm text-zinc-400 text-right">
                              <div className="font-bold">₹{item.cgst_amount.toFixed(2)}</div>
                              <div className="text-xs font-bold text-zinc-600">({item.gst_rate / 2}%)</div>
                            </td>
                            <td className="px-4 py-4 text-sm text-zinc-400 text-right">
                              <div className="font-bold">₹{item.sgst_amount.toFixed(2)}</div>
                              <div className="text-xs font-bold text-zinc-600">({item.gst_rate / 2}%)</div>
                            </td>
                          </>
                        ) : (
                          <td className="px-4 py-4 text-sm text-zinc-400 text-right">
                            <div className="font-bold">₹{(item.igst_amount || 0).toFixed(2)}</div>
                            <div className="text-xs font-bold text-zinc-600">({item.gst_rate}%)</div>
                          </td>
                        )}
                        <td className="px-4 py-4 text-sm text-lime-400 text-right font-black">₹{item.total.toFixed(2)}</td>
                        <td className="px-4 py-4 text-right">
                          <button onClick={() => removeItem(item.product_id)} className="text-rose-500 hover:text-rose-400 transition-colors p-2 hover:bg-rose-500/10 rounded-lg" aria-label={`Remove ${item.product_name} from bill`} title={`Remove ${item.product_name}`}>
                            <Trash2 className="h-5 w-5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          
          <div className="bg-zinc-950/50 p-6 border-t-2 border-zinc-800 rounded-b-2xl">
            <div className="space-y-3">
              <div className="flex justify-between text-sm font-bold text-zinc-400">
                <span className="uppercase tracking-wider">Subtotal (excl. GST)</span>
                <span>₹{subtotal.toFixed(2)}</span>
              </div>
              {!isInterState ? (
                <>
                  <div className="flex justify-between text-sm font-bold text-zinc-400">
                    <span className="uppercase tracking-wider">CGST</span>
                    <span>₹{totalCgst.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between text-sm font-bold text-zinc-400">
                    <span className="uppercase tracking-wider">SGST</span>
                    <span>₹{totalSgst.toFixed(2)}</span>
                  </div>
                </>
              ) : (
                <div className="flex justify-between text-sm font-bold text-zinc-400">
                  <span className="uppercase tracking-wider">IGST</span>
                  <span>₹{totalIgst.toFixed(2)}</span>
                </div>
              )}
              <div className="flex justify-between text-sm font-bold text-zinc-400 items-center bg-zinc-900 p-3 rounded-xl border-2 border-zinc-800">
                <span className="uppercase tracking-wider">Discount</span>
                <div className="flex items-center space-x-2">
                  <select
                    value={discountType}
                    onChange={(e) => setDiscountType(e.target.value as 'value' | 'percentage')}
                    className="bg-zinc-950 border-2 border-zinc-800 rounded-lg text-zinc-300 text-sm font-bold focus:ring-lime-400 focus:border-lime-400 py-1 pl-2 pr-8"
                    aria-label="Discount type"
                  >
                    <option value="value">₹</option>
                    <option value="percentage">%</option>
                  </select>
                  <input
                    type="number"
                    min="0"
                    value={discount}
                    onChange={(e) => setDiscount(parseFloat(e.target.value) || 0)}
                    className="w-24 text-right sm:text-sm font-bold bg-zinc-950 border-2 border-zinc-800 rounded-lg focus:ring-lime-400 focus:border-lime-400 text-white py-1 px-2"
                  />
                </div>
              </div>
              <div className="flex justify-between text-2xl font-black text-white pt-4 border-t-2 border-zinc-800 mt-4">
                <span className="uppercase tracking-wider">Grand Total</span>
                <span className="text-lime-400">₹{grandTotal.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-lg font-bold text-zinc-400 pt-4 border-t-2 border-zinc-800 mt-4 items-center">
                <span className="uppercase tracking-wider">Amount Paid</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  className="w-32 text-right sm:text-sm bg-zinc-950 border-2 border-zinc-800 rounded-lg p-2 text-white font-bold focus:ring-lime-400 focus:border-lime-400"
                  placeholder={grandTotal.toFixed(2)}
                  value={amountPaid}
                  onChange={(e) => setAmountPaid(e.target.value)}
                />
              </div>
            </div>
            <div className="mt-6">
              <button
                onClick={handleSave}
                disabled={isSaving}
                className="w-full flex justify-center items-center py-4 px-4 border-2 border-zinc-950 rounded-xl shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] text-lg font-black text-zinc-950 bg-lime-400 hover:bg-lime-300 hover:translate-y-[-2px] hover:translate-x-[-2px] hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:hover:translate-x-0 disabled:hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] transition-all uppercase tracking-wider"
              >
                {isSaving ? (
                  <>
                    <Loader2 className="animate-spin h-6 w-6 mr-2" />
                    Saving...
                  </>
                ) : (
                  'Save & Generate Invoice'
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
