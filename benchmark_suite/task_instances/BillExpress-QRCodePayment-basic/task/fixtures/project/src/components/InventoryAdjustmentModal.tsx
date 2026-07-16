import React, { useState, useEffect } from "react";
import { X, Save, History, Loader2, AlertCircle } from "lucide-react";
import { apiFetch } from "../utils/api.js";
import { Product } from "../types.js";

interface Transaction {
  id: number;
  type: string;
  quantity: number;
  reason: string | null;
  date: string;
}

interface Props {
  product: Product;
  onClose: () => void;
  onSuccess: () => void;
}

export default function InventoryAdjustmentModal({
  product,
  onClose,
  onSuccess,
}: Props) {
  const [activeTab, setActiveTab] = useState<"adjust" | "history">("adjust");
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const [formData, setFormData] = useState({
    type: "restock",
    quantity: "",
    reason: "",
  });

  useEffect(() => {
    if (activeTab === "history") {
      fetchHistory();
    }
  }, [activeTab]);

  const fetchHistory = async () => {
    setIsHistoryLoading(true);
    try {
      const res = await apiFetch(`/api/products/${product.id}/transactions`);
      const data = await res.json();
      setTransactions(data);
    } catch (err) {
      console.error(err);
    } finally {
      setIsHistoryLoading(false);
    }
  };

  const handleAdjust = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      const qty = parseFloat(formData.quantity);
      // For deductions, ensure quantity is negative if type is not restock/return
      const adjustedQty =
        formData.type === "damage" ||
        (formData.type === "adjustment" && qty < 0)
          ? -Math.abs(qty)
          : qty;

      const res = await apiFetch(
        `/api/products/${product.id}/stock-adjustment`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            type: formData.type,
            quantity: adjustedQty,
            reason: formData.reason,
          }),
        },
      );

      if (res.ok) {
        onSuccess();
        onClose();
      } else {
        const error = await res.json();
        alert(`Error: ${error.error || "Failed to adjust stock"}`);
      }
    } catch (err) {
      console.error(err);
      alert("An error occurred while adjusting stock");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-60 overflow-y-auto">
      <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
        <div
          className="fixed inset-0 transition-opacity z-0"
          aria-hidden="true"
          onClick={onClose}
        >
          <div className="absolute inset-0 bg-zinc-950 opacity-75 backdrop-blur-sm"></div>
        </div>
        <span
          className="hidden sm:inline-block sm:align-middle sm:h-screen"
          aria-hidden="true"
        >
          &#8203;
        </span>

        <div className="relative z-10 inline-block align-bottom bg-zinc-900 border-2 border-zinc-800 rounded-2xl text-left overflow-hidden shadow-2xl transform transition-all sm:my-8 sm:align-middle sm:max-w-2xl sm:w-full">
          <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 bg-zinc-950/50">
            <div>
              <h3 className="text-xl font-black text-white">{product.name}</h3>
              <p className="text-sm text-zinc-400 font-mono">
                {product.code} • Current Stock:{" "}
                <span className="text-lime-400 font-bold">
                  {product.stock} {product.unit}
                </span>
              </p>
            </div>
            <button
              onClick={onClose}
              className="text-zinc-500 hover:text-white transition-colors"
              aria-label="Close modal"
              title="Close modal"
            >
              <X className="h-6 w-6" />
            </button>
          </div>

          <div className="flex border-b border-zinc-800">
            <button
              onClick={() => setActiveTab("adjust")}
              className={`flex-1 py-4 text-sm font-bold uppercase tracking-wider transition-colors ${activeTab === "adjust" ? "bg-zinc-800 text-lime-400 border-b-2 border-lime-400" : "text-zinc-500 hover:text-zinc-300"}`}
            >
              Adjust Stock
            </button>
            <button
              onClick={() => setActiveTab("history")}
              className={`flex-1 py-4 text-sm font-bold uppercase tracking-wider transition-colors ${activeTab === "history" ? "bg-zinc-800 text-lime-400 border-b-2 border-lime-400" : "text-zinc-500 hover:text-zinc-300"}`}
            >
              History
            </button>
          </div>

          <div className="p-6">
            {activeTab === "adjust" ? (
              <form onSubmit={handleAdjust} className="space-y-6">
                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <label
                      htmlFor="adj-type"
                      className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2"
                    >
                      Adjustment Type
                    </label>
                    <select
                      id="adj-type"
                      value={formData.type}
                      onChange={(e) =>
                        setFormData({ ...formData, type: e.target.value })
                      }
                      className="block w-full bg-zinc-950 border-2 border-zinc-800 rounded-lg p-2 text-white focus:ring-lime-400 outline-none"
                      required
                    >
                      <option value="restock">Restock / Purchase (+)</option>
                      <option value="return">Return (+)</option>
                      <option value="damage">Damage (-)</option>
                      <option value="adjustment">
                        Manual Adjustment (+/-)
                      </option>
                    </select>
                  </div>
                  <div>
                    <label
                      htmlFor="adj-qty"
                      className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2"
                    >
                      Quantity ({product.unit})
                    </label>
                    <input
                      id="adj-qty"
                      type="number"
                      step="0.01"
                      value={formData.quantity}
                      onChange={(e) =>
                        setFormData({ ...formData, quantity: e.target.value })
                      }
                      className="block w-full bg-zinc-950 border-2 border-zinc-800 rounded-lg p-2 text-white focus:ring-lime-400 outline-none"
                      placeholder="Enter amount..."
                      required
                    />
                  </div>
                </div>
                <div>
                  <label
                    htmlFor="adj-reason"
                    className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2"
                  >
                    Reason / Note
                  </label>
                  <textarea
                    id="adj-reason"
                    value={formData.reason}
                    onChange={(e) =>
                      setFormData({ ...formData, reason: e.target.value })
                    }
                    rows={3}
                    className="block w-full bg-zinc-950 border-2 border-zinc-800 rounded-lg p-2 text-white focus:ring-lime-400 outline-none"
                    placeholder="Why is this adjustment being made?"
                    required
                  />
                </div>
                <div className="pt-4 flex justify-end gap-4">
                  <button
                    type="button"
                    onClick={onClose}
                    className="px-6 py-2 border-2 border-zinc-700 rounded-xl font-bold text-zinc-400 hover:bg-zinc-800 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSaving}
                    className="inline-flex items-center px-8 py-2 border-2 border-zinc-950 rounded-xl shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] text-zinc-950 bg-lime-400 hover:bg-lime-300 transition-all font-black uppercase disabled:opacity-50"
                  >
                    {isSaving ? (
                      <Loader2 className="animate-spin h-5 w-5" />
                    ) : (
                      <Save className="mr-2 h-5 w-5" />
                    )}
                    Save Adjustment
                  </button>
                </div>
              </form>
            ) : (
              <div className="space-y-4 max-h-96 overflow-y-auto pr-2">
                {isHistoryLoading ? (
                  <div className="flex justify-center py-12">
                    <Loader2 className="animate-spin h-8 w-8 text-lime-400" />
                  </div>
                ) : transactions.length === 0 ? (
                  <div className="text-center py-12 text-zinc-500">
                    <History className="h-12 w-12 mx-auto mb-4 opacity-20" />
                    <p>No transaction history found for this product.</p>
                  </div>
                ) : (
                  <table className="min-w-full divide-y divide-zinc-800">
                    <thead>
                      <tr>
                        <th className="text-left text-xs font-bold text-zinc-500 uppercase py-2">
                          Date
                        </th>
                        <th className="text-left text-xs font-bold text-zinc-500 uppercase py-2">
                          Type
                        </th>
                        <th className="text-right text-xs font-bold text-zinc-500 uppercase py-2">
                          Qty
                        </th>
                        <th className="text-left text-xs font-bold text-zinc-500 uppercase py-2 pl-4">
                          Reason
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-800/50">
                      {transactions.map((t) => (
                        <tr key={t.id}>
                          <td className="py-3 text-xs text-zinc-400">
                            {new Date(t.date).toLocaleDateString()}
                          </td>
                          <td className="py-3">
                            <span
                              className={`text-[10px] font-black uppercase px-2 py-0.5 rounded ${
                                t.type === "restock" || t.type === "return"
                                  ? "bg-lime-400/10 text-lime-400"
                                  : t.type === "sale"
                                    ? "bg-cyan-400/10 text-cyan-400"
                                    : "bg-rose-400/10 text-rose-400"
                              }`}
                            >
                              {t.type}
                            </span>
                          </td>
                          <td
                            className={`py-3 text-right font-bold text-sm ${t.quantity > 0 ? "text-lime-400" : "text-rose-400"}`}
                          >
                            {t.quantity > 0 ? `+${t.quantity}` : t.quantity}
                          </td>
                          <td
                            className="py-3 text-xs text-zinc-300 pl-4 italic truncate max-w-[200px]"
                            title={t.reason || ""}
                          >
                            {t.reason || "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
