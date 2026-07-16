import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Eye, Search, Download, XCircle, Receipt } from 'lucide-react';
import { format } from 'date-fns';
import { apiFetch } from '../utils/api.js';
import { Invoice } from '../types.js';

export default function Invoices() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [totalInvoices, setTotalInvoices] = useState(0);
  const [page, setPage] = useState(1);
  const limit = 50;

  const [search, setSearch] = useState('');
  const [dateFilter, setDateFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');

  const fetchInvoices = useCallback(async () => {
    const params = new URLSearchParams({
      page: page.toString(),
      limit: limit.toString(),
      search: search,
      dateFilter: dateFilter,
      typeFilter: typeFilter
    });
    try {
      const res = await apiFetch(`/api/invoices?${params}`);
      const data = await res.json();
      if (data.data) {
        setInvoices(data.data);
        setTotalInvoices(data.total);
      } else {
        setInvoices(Array.isArray(data) ? data : []);
        setTotalInvoices(Array.isArray(data) ? data.length : 0);
      }
    } catch (err) {
      console.error('Failed to fetch invoices', err);
    }
  }, [page, limit, search, dateFilter, typeFilter]);

  const fetchInvoicesRef = useRef(fetchInvoices);
  useEffect(() => {
    fetchInvoicesRef.current = fetchInvoices;
  }, [fetchInvoices]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchInvoices();
    }, 300); // Debounce fetch on search
    return () => clearTimeout(timer);
  }, [fetchInvoices]);

  const handleCancel = useCallback(async (id: number) => {
    if (confirm('Are you sure you want to void this invoice? This will restore stock and mark it as cancelled.')) {
      try {
        await apiFetch(`/api/invoices/${id}/cancel`, { method: 'PUT' });
        fetchInvoicesRef.current();
      } catch (err) {
        alert('Failed to cancel invoice');
      }
    }
  }, []);

  const handlePayment = useCallback(async (id: number, currentAmount: number, total: number) => {
    const amount = prompt(`Enter amount paid (Total: ₹${total}, Current: ₹${currentAmount}):`, currentAmount.toString());
    if (amount !== null) {
      const parsedAmount = parseFloat(amount);
      if (!isNaN(parsedAmount)) {
        const status = parsedAmount >= total ? 'Paid' : parsedAmount > 0 ? 'Partial' : 'Unpaid';
        try {
          await apiFetch(`/api/invoices/${id}/payment`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ payment_status: status, amount_paid: parsedAmount })
          });
          fetchInvoicesRef.current();
        } catch (err) {
          alert('Failed to update payment');
        }
      }
    }
  }, []);

  const [isExporting, setIsExporting] = useState(false);

  const handleExportCSV = async () => {
    setIsExporting(true);
    try {
      const params = new URLSearchParams({
        page: '1',
        limit: '10000', // Fetch up to 10k records for export
        search: search,
        dateFilter: dateFilter,
        typeFilter: typeFilter
      });
      const res = await apiFetch(`/api/invoices?${params}`);
      const data = await res.json();
      const exportData = data.data || [];

      const headers = ['Invoice No', 'Date', 'Customer', 'Type', 'Status', 'Payment Status', 'Amount Paid', 'Total Amount'];
      const csvContent = [
        headers.join(','),
        ...exportData.map((i: Invoice) => [
          `"${i.invoice_number}"`,
          `"${format(new Date(i.date), 'yyyy-MM-dd')}"`,
          `"${i.customer_name || 'Cash Sale'}"`,
          `"${i.type}"`,
          `"${i.status}"`,
          `"${i.payment_status}"`,
          i.amount_paid,
          i.grand_total
        ].join(','))
      ].join('\n');

      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'invoices.csv';
      link.click();
    } catch (err) {
      console.error('Failed to export invoices', err);
      alert('Failed to export invoices');
    } finally {
      setIsExporting(false);
    }
  };

  // ⚡ Bolt: Memoize the 50 table rows to prevent re-rendering them on every single keystroke in the search input
  const renderedInvoices = useMemo(() => {
    return invoices.map((invoice: Invoice) => (
      <tr key={invoice.id} className="hover:bg-zinc-800/50 transition-colors">
        <td className="px-6 py-4 whitespace-nowrap text-sm font-bold text-white">{invoice.invoice_number}</td>
        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-zinc-400">
          {format(new Date(invoice.date), 'dd MMM yyyy')}
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-zinc-300">
          {invoice.customer_name || 'Cash Sale'}
          {invoice.customer_mobile && <span className="block text-xs text-zinc-500 mt-1">{invoice.customer_mobile}</span>}
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-zinc-400">
          <div className="flex flex-col gap-1">
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-zinc-800 text-zinc-300 border border-zinc-700 capitalize w-fit">
              {invoice.type}
            </span>
            {invoice.status === 'cancelled' && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-500/10 text-rose-500 border border-rose-500/20 capitalize w-fit">
                Void
              </span>
            )}
          </div>
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-lime-400 text-right font-bold">
          <span className={invoice.status === 'cancelled' ? 'line-through text-zinc-500' : ''}>
            ₹{invoice.grand_total.toFixed(2)}
          </span>
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-right">
          <button
            onClick={() => handlePayment(invoice.id, invoice.amount_paid, invoice.grand_total)}
            disabled={invoice.status === 'cancelled'}
            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold border transition-colors ${
              invoice.payment_status === 'Paid' ? 'bg-lime-400/10 text-lime-400 border-lime-400/20 hover:bg-lime-400/20' :
              invoice.payment_status === 'Partial' ? 'bg-amber-400/10 text-amber-400 border-amber-400/20 hover:bg-amber-400/20' :
              'bg-rose-500/10 text-rose-500 border-rose-500/20 hover:bg-rose-500/20'
            } ${invoice.status === 'cancelled' ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            {invoice.payment_status} (₹{invoice.amount_paid?.toFixed(2) || '0.00'})
          </button>
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
          <Link to={`/invoices/${invoice.id}`} className="text-cyan-400 hover:text-cyan-300 mr-4 inline-flex items-center transition-colors" aria-label={`View invoice ${invoice.invoice_number}`} title="View invoice details">
            <Eye className="h-5 w-5" />
          </Link>
          {invoice.status === 'active' && (
            <button onClick={() => handleCancel(invoice.id)} className="text-rose-500 hover:text-rose-400 inline-flex items-center transition-colors" title={`Void Invoice ${invoice.invoice_number}`} aria-label={`Void Invoice ${invoice.invoice_number}`}>
              <XCircle className="h-5 w-5" />
            </button>
          )}
        </td>
      </tr>
    ));
  }, [invoices, handlePayment, handleCancel]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-black tracking-tight text-white">Invoices</h1>
        <button
          onClick={handleExportCSV}
          disabled={isExporting}
          className="inline-flex items-center px-4 py-2 border-2 border-zinc-950 text-sm font-bold rounded-xl shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] text-zinc-950 bg-cyan-400 hover:bg-cyan-300 hover:translate-y-[-2px] hover:translate-x-[-2px] hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] transition-all disabled:opacity-50"
        >
          <Download className="-ml-1 mr-2 h-4 w-4" />
          {isExporting ? 'Exporting...' : 'Export CSV'}
        </button>
      </div>

      <div className="bg-zinc-900 border-2 border-zinc-800 rounded-2xl p-6">
        <div className="flex flex-col sm:flex-row gap-4 mb-6">
          <div className="relative flex-1">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Search className="h-5 w-5 text-zinc-500" />
            </div>
            <input
              type="text"
              aria-label="Search invoices"
              className="block w-full pl-10 sm:text-sm"
              placeholder="Search by invoice #, name, or mobile..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <select
            value={dateFilter}
            onChange={(e) => {
              setDateFilter(e.target.value);
              setPage(1);
            }}
            className="block w-full sm:w-48 sm:text-sm"
            aria-label="Filter by date"
          >
            <option value="all">All Time</option>
            <option value="today">Today</option>
            <option value="month">This Month</option>
          </select>
          <select
            value={typeFilter}
            onChange={(e) => {
              setTypeFilter(e.target.value);
              setPage(1);
            }}
            className="block w-full sm:w-48 sm:text-sm"
            aria-label="Filter by invoice type"
          >
            <option value="all">All Types</option>
            <option value="b2b">B2B</option>
            <option value="b2c">B2C</option>
            <option value="cash">Cash</option>
          </select>
        </div>

        <div className="flex flex-col">
          <div className="-my-2 overflow-x-auto sm:-mx-6 lg:-mx-8">
            <div className="py-2 align-middle inline-block min-w-full sm:px-6 lg:px-8">
              <div className="bg-zinc-900 border-2 border-zinc-800 overflow-hidden rounded-2xl">
                <table className="min-w-full divide-y divide-zinc-800">
                  <thead className="bg-zinc-950/50">
                    <tr>
                      <th scope="col" className="px-6 py-4 text-left text-xs font-bold text-zinc-400 uppercase tracking-wider">Invoice No</th>
                      <th scope="col" className="px-6 py-4 text-left text-xs font-bold text-zinc-400 uppercase tracking-wider">Date</th>
                      <th scope="col" className="px-6 py-4 text-left text-xs font-bold text-zinc-400 uppercase tracking-wider">Customer</th>
                      <th scope="col" className="px-6 py-4 text-left text-xs font-bold text-zinc-400 uppercase tracking-wider">Type/Status</th>
                      <th scope="col" className="px-6 py-4 text-right text-xs font-bold text-zinc-400 uppercase tracking-wider">Amount</th>
                      <th scope="col" className="px-6 py-4 text-right text-xs font-bold text-zinc-400 uppercase tracking-wider">Payment</th>
                      <th scope="col" className="relative px-6 py-4"><span className="sr-only">Actions</span></th>
                    </tr>
                  </thead>
                  <tbody className="bg-zinc-900 divide-y divide-zinc-800">
                    {invoices.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="px-6 py-16 text-center">
                          <div className="flex flex-col items-center justify-center">
                            {(search !== '' || dateFilter !== 'all' || typeFilter !== 'all') ? (
                              <>
                                <div className="bg-zinc-800/50 p-4 rounded-full mb-4">
                                  <Search className="h-8 w-8 text-zinc-500" />
                                </div>
                                <h3 className="text-lg font-bold text-white mb-2">No matching invoices</h3>
                                <p className="text-zinc-400 text-sm mb-6 max-w-sm mx-auto">
                                  We couldn't find any invoices matching your current search and filter criteria.
                                </p>
                                <button
                                  onClick={() => {
                                    setSearch('');
                                    setDateFilter('all');
                                    setTypeFilter('all');
                                    setPage(1);
                                  }}
                                  className="inline-flex items-center px-4 py-2 border-2 border-zinc-800 text-sm font-bold rounded-xl text-zinc-300 bg-zinc-950 hover:bg-zinc-800 transition-colors"
                                >
                                  Clear Filters
                                </button>
                              </>
                            ) : (
                              <>
                                <div className="bg-zinc-800/50 p-4 rounded-full mb-4">
                                  <Receipt className="h-8 w-8 text-zinc-500" />
                                </div>
                                <h3 className="text-lg font-bold text-white mb-2">No invoices yet</h3>
                                <p className="text-zinc-400 text-sm mb-6 max-w-sm mx-auto">
                                  Get started by creating your first bill.
                                </p>
                                <Link
                                  to="/new-bill"
                                  className="inline-flex items-center px-4 py-2 border-2 border-zinc-950 text-sm font-bold rounded-xl shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] text-zinc-950 bg-lime-400 hover:bg-lime-300 hover:translate-y-[-2px] hover:translate-x-[-2px] hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] transition-all"
                                >
                                  Create New Bill
                                </Link>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ) : (
                      renderedInvoices
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Pagination Controls */}
      {(() => {
        const totalPages = Math.ceil(totalInvoices / limit);
        return totalPages > 1 ? (
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
                  Showing <span className="font-medium text-white">{((page - 1) * limit) + 1}</span> to <span className="font-medium text-white">{Math.min(page * limit, totalInvoices)}</span> of <span className="font-medium text-white">{totalInvoices}</span> results
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
        ) : null;
      })()}
    </div>
  );
}
