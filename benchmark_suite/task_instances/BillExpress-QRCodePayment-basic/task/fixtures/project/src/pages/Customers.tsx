import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Search, Edit2, Save, X, Download } from 'lucide-react';
import { apiFetch } from '../utils/api.js';
import { Customer } from '../types.js';

export default function Customers() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [totalCustomers, setTotalCustomers] = useState(0);
  const [page, setPage] = useState(1);
  const limit = 50;

  const [search, setSearch] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<Partial<Customer>>({});

  const fetchCustomers = useCallback(async () => {
    const params = new URLSearchParams({
      page: page.toString(),
      limit: limit.toString(),
      search: search
    });
    try {
      const res = await apiFetch(`/api/customers?${params}`);
      const data = await res.json();
      if (data.data) {
        setCustomers(data.data);
        setTotalCustomers(data.total);
      } else {
        setCustomers(Array.isArray(data) ? data : []);
        setTotalCustomers(Array.isArray(data) ? data.length : 0);
      }
    } catch (err) {
      console.error('Failed to fetch customers', err);
    }
  }, [page, limit, search]);

  const fetchCustomersRef = useRef(fetchCustomers);
  useEffect(() => {
    fetchCustomersRef.current = fetchCustomers;
  }, [fetchCustomers]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchCustomers();
    }, 300); // Debounce fetch on search
    return () => clearTimeout(timer);
  }, [fetchCustomers]);

  const handleEdit = useCallback((customer: Customer) => {
    setEditingId(customer.id);
    setEditForm(customer);
  }, []);

  const handleSave = useCallback(async () => {
    try {
      await apiFetch(`/api/customers/${editingId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editForm)
      });
      setEditingId(null);
      fetchCustomersRef.current();
    } catch (err) {
      console.error(err);
      alert('Failed to update customer');
    }
  }, [editingId, editForm]);

  const [isExporting, setIsExporting] = useState(false);

  const handleExportCSV = async () => {
    setIsExporting(true);
    try {
      const params = new URLSearchParams({
        page: '1',
        limit: '10000', // Fetch up to 10k records for export
        search: search
      });
      const res = await apiFetch(`/api/customers?${params}`);
      const data = await res.json();
      const exportData = data.data || [];

      const headers = ['Name', 'Mobile', 'Address', 'GSTIN', 'State', 'Lifetime Value'];
      const csvContent = [
        headers.join(','),
        ...exportData.map((c: Customer) => [
          `"${c.name}"`,
          `"${c.mobile || ''}"`,
          `"${c.address || ''}"`,
          `"${c.gstin || ''}"`,
          `"${c.state || ''}"`,
          c.lifetime_value
        ].join(','))
      ].join('\n');

      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'customers.csv';
      link.click();
    } catch (err) {
      console.error('Failed to export customers', err);
      alert('Failed to export customers');
    } finally {
      setIsExporting(false);
    }
  };

  const totalPages = Math.ceil(totalCustomers / limit);

  // ⚡ Bolt: Memoize the 50 table rows to prevent re-rendering them on every single keystroke in the search input
  const renderedCustomers = useMemo(() => {
    return customers.map((customer: Customer) => (
      <tr key={customer.id} className="hover:bg-zinc-800/50 transition-colors">
        {editingId === customer.id ? (
          <>
            <td className="px-6 py-4 whitespace-nowrap">
              <input type="text" value={editForm.name} onChange={e => setEditForm({...editForm, name: e.target.value})} className="w-full sm:text-sm" />
            </td>
            <td className="px-6 py-4 whitespace-nowrap">
              <input type="text" value={editForm.mobile} onChange={e => setEditForm({...editForm, mobile: e.target.value})} className="w-full sm:text-sm" />
            </td>
            <td className="px-6 py-4 whitespace-nowrap">
              <input type="text" value={editForm.address} onChange={e => setEditForm({...editForm, address: e.target.value})} className="w-full sm:text-sm mb-1" placeholder="Address" />
              <input type="text" value={editForm.state} onChange={e => setEditForm({...editForm, state: e.target.value})} className="w-full sm:text-sm" placeholder="State" />
            </td>
            <td className="px-6 py-4 whitespace-nowrap">
              <input type="text" value={editForm.gstin} onChange={e => setEditForm({...editForm, gstin: e.target.value})} className="w-full sm:text-sm" />
            </td>
            <td className="px-6 py-4 whitespace-nowrap text-sm text-lime-400 text-right font-bold">₹{customer.lifetime_value.toFixed(2)}</td>
            <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
              <button onClick={handleSave} className="text-lime-400 hover:text-lime-300 mr-3" aria-label="Save changes" title="Save changes"><Save className="h-5 w-5" /></button>
              <button onClick={() => setEditingId(null)} className="text-zinc-400 hover:text-zinc-300" aria-label="Cancel editing" title="Cancel editing"><X className="h-5 w-5" /></button>
            </td>
          </>
        ) : (
          <>
            <td className="px-6 py-4 whitespace-nowrap text-sm font-bold text-white">{customer.name}</td>
            <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-zinc-400">{customer.mobile || '-'}</td>
            <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-zinc-400">
              {customer.address || '-'}
              {customer.state && <span className="block text-xs text-zinc-500 mt-1">{customer.state}</span>}
            </td>
            <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-zinc-400">{customer.gstin || '-'}</td>
            <td className="px-6 py-4 whitespace-nowrap text-sm text-lime-400 text-right font-bold">₹{customer.lifetime_value.toFixed(2)}</td>
            <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
              <button onClick={() => handleEdit(customer)} className="text-cyan-400 hover:text-cyan-300 inline-flex items-center transition-colors" aria-label="Edit customer" title="Edit customer">
                <Edit2 className="h-5 w-5" />
              </button>
            </td>
          </>
        )}
      </tr>
    ));
  }, [customers, editingId, editForm, handleEdit, handleSave]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-black tracking-tight text-white">Customers</h1>
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
        <div className="flex items-center mb-6">
          <div className="relative w-full max-w-md">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Search className="h-5 w-5 text-zinc-500" />
            </div>
            <input
              type="text"
              aria-label="Search customers"
              className="block w-full pl-10 sm:text-sm"
              placeholder="Search by name or mobile..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
        </div>

        <div className="flex flex-col">
          <div className="-my-2 overflow-x-auto sm:-mx-6 lg:-mx-8">
            <div className="py-2 align-middle inline-block min-w-full sm:px-6 lg:px-8">
              <div className="bg-zinc-900 border-2 border-zinc-800 overflow-hidden rounded-2xl">
                <table className="min-w-full divide-y divide-zinc-800">
                  <thead className="bg-zinc-950/50">
                    <tr>
                      <th scope="col" className="px-6 py-4 text-left text-xs font-bold text-zinc-400 uppercase tracking-wider">Name</th>
                      <th scope="col" className="px-6 py-4 text-left text-xs font-bold text-zinc-400 uppercase tracking-wider">Mobile</th>
                      <th scope="col" className="px-6 py-4 text-left text-xs font-bold text-zinc-400 uppercase tracking-wider">Address/State</th>
                      <th scope="col" className="px-6 py-4 text-left text-xs font-bold text-zinc-400 uppercase tracking-wider">GSTIN</th>
                      <th scope="col" className="px-6 py-4 text-right text-xs font-bold text-zinc-400 uppercase tracking-wider">Lifetime Value</th>
                      <th scope="col" className="relative px-6 py-4"><span className="sr-only">Actions</span></th>
                    </tr>
                  </thead>
                  <tbody className="bg-zinc-900 divide-y divide-zinc-800">
                    {renderedCustomers}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        {totalCustomers > 0 && (
          <div className="mt-6 flex items-center justify-between border-t-2 border-zinc-800 pt-4">
            <div className="flex-1 flex justify-between sm:hidden">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="relative inline-flex items-center px-4 py-2 border-2 border-zinc-800 text-sm font-bold rounded-xl text-white bg-zinc-900 hover:bg-zinc-800 disabled:opacity-50"
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="ml-3 relative inline-flex items-center px-4 py-2 border-2 border-zinc-800 text-sm font-bold rounded-xl text-white bg-zinc-900 hover:bg-zinc-800 disabled:opacity-50"
              >
                Next
              </button>
            </div>
            <div className="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
              <div>
                <p className="text-sm text-zinc-400">
                  Showing <span className="font-medium text-white">{((page - 1) * limit) + 1}</span> to <span className="font-medium text-white">{Math.min(page * limit, totalCustomers)}</span> of <span className="font-medium text-white">{totalCustomers}</span> results
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

      </div>
    </div>
  );
}
