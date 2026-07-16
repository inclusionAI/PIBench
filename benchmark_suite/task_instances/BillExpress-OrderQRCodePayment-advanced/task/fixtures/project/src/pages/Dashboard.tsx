import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Receipt, TrendingUp, Package, Users, AlertTriangle } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';
import { apiFetch } from '../utils/api.js';
import { Invoice, Product, Customer, AnalyticsData, DashboardStats } from '../types.js';

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats>({
    todaySales: 0,
    todayInvoices: 0,
    totalProducts: 0,
    totalCustomers: 0,
  });
  
  const [analytics, setAnalytics] = useState<AnalyticsData>({
    last7Days: [],
    topProducts: [],
    lowStock: []
  });

  useEffect(() => {
    apiFetch('/api/dashboard/analytics')
      .then(res => res.json())
      .then(data => {
        // ⚡ Bolt: Consolidate multiple data-fetching requests into unified analytics endpoint
        // to reduce network payload and client-side processing.
        setStats(s => ({
          ...s,
          todaySales: data.todaySales,
          todayInvoices: data.todayInvoices,
          totalProducts: data.totalProducts,
          totalCustomers: data.totalCustomers,
        }));
        setAnalytics({
          last7Days: data.last7Days,
          topProducts: data.topProducts,
          lowStock: data.lowStock
        });
      });
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-black tracking-tight text-white">Dashboard</h1>
        <Link
          to="/new-bill"
          className="inline-flex items-center px-6 py-3 border-2 border-zinc-950 text-sm font-bold rounded-xl shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] text-zinc-950 bg-lime-400 hover:bg-lime-300 hover:translate-y-[-2px] hover:translate-x-[-2px] hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] transition-all"
        >
          <Receipt className="-ml-1 mr-2 h-5 w-5" />
          Create New Bill
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <div className="bg-zinc-900 border-2 border-zinc-800 overflow-hidden rounded-2xl hover:border-lime-400 transition-colors">
          <div className="p-6">
            <div className="flex items-center">
              <div className="shrink-0 bg-lime-400/10 p-3 rounded-xl">
                <TrendingUp className="h-6 w-6 text-lime-400" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Today's Sales</dt>
                  <dd className="flex items-baseline mt-1">
                    <div className="text-3xl font-black text-white">
                      ₹{stats.todaySales.toFixed(2)}
                    </div>
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-zinc-900 border-2 border-zinc-800 overflow-hidden rounded-2xl hover:border-cyan-400 transition-colors">
          <div className="p-6">
            <div className="flex items-center">
              <div className="shrink-0 bg-cyan-400/10 p-3 rounded-xl">
                <Receipt className="h-6 w-6 text-cyan-400" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Today's Invoices</dt>
                  <dd className="flex items-baseline mt-1">
                    <div className="text-3xl font-black text-white">
                      {stats.todayInvoices}
                    </div>
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-zinc-900 border-2 border-zinc-800 overflow-hidden rounded-2xl hover:border-fuchsia-400 transition-colors">
          <div className="p-6">
            <div className="flex items-center">
              <div className="shrink-0 bg-fuchsia-400/10 p-3 rounded-xl">
                <Package className="h-6 w-6 text-fuchsia-400" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Total Products</dt>
                  <dd className="flex items-baseline mt-1">
                    <div className="text-3xl font-black text-white">
                      {stats.totalProducts}
                    </div>
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-zinc-900 border-2 border-zinc-800 overflow-hidden rounded-2xl hover:border-amber-400 transition-colors">
          <div className="p-6">
            <div className="flex items-center">
              <div className="shrink-0 bg-amber-400/10 p-3 rounded-xl">
                <Users className="h-6 w-6 text-amber-400" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Total Customers</dt>
                  <dd className="flex items-baseline mt-1">
                    <div className="text-3xl font-black text-white">
                      {stats.totalCustomers}
                    </div>
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Sales Chart */}
        <div className="bg-zinc-900 border-2 border-zinc-800 rounded-2xl p-6">
          <h2 className="text-xl font-black text-white mb-6 uppercase tracking-wider">Sales (Last 7 Days)</h2>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={analytics.last7Days}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis dataKey="day" stroke="#a1a1aa" fontSize={12} tickFormatter={(val) => val.split('-').slice(1).join('/')} />
                <YAxis stroke="#a1a1aa" fontSize={12} tickFormatter={(val) => `₹${val}`} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#18181b', borderColor: '#27272a', borderRadius: '0.75rem' }}
                  itemStyle={{ color: '#a3e635', fontWeight: 'bold' }}
                />
                <Line type="monotone" dataKey="sales" stroke="#a3e635" strokeWidth={3} dot={{ r: 4, fill: '#a3e635' }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Top Products */}
        <div className="bg-zinc-900 border-2 border-zinc-800 rounded-2xl p-6">
          <h2 className="text-xl font-black text-white mb-6 uppercase tracking-wider">Top Selling Products</h2>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={analytics.topProducts} layout="vertical" margin={{ left: 40 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" horizontal={true} vertical={false} />
                <XAxis type="number" stroke="#a1a1aa" fontSize={12} />
                <YAxis dataKey="name" type="category" stroke="#a1a1aa" fontSize={12} width={100} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#18181b', borderColor: '#27272a', borderRadius: '0.75rem' }}
                  itemStyle={{ color: '#22d3ee', fontWeight: 'bold' }}
                  cursor={{ fill: '#27272a' }}
                />
                <Bar dataKey="qty" fill="#22d3ee" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Low Stock Alerts */}
      {analytics.lowStock.length > 0 && (
        <div className="bg-rose-500/10 border-2 border-rose-500 rounded-2xl p-6">
          <div className="flex items-center mb-4">
            <AlertTriangle className="h-6 w-6 text-rose-500 mr-2" />
            <h2 className="text-xl font-black text-rose-500 uppercase tracking-wider">Low Stock Alerts</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {analytics.lowStock.map((item: Product) => (
              <div key={item.id} className="bg-zinc-950 border-2 border-rose-500/50 rounded-xl p-4 flex justify-between items-center">
                <div>
                  <p className="font-bold text-white">{item.name}</p>
                  <p className="text-xs text-zinc-400 font-mono mt-1">{item.code}</p>
                </div>
                <div className="text-right">
                  <p className="text-2xl font-black text-rose-500">{item.stock}</p>
                  <p className="text-xs text-zinc-500 uppercase">{item.unit}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
