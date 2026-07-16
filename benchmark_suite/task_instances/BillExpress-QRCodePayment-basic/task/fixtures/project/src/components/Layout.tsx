import { useState } from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { LayoutDashboard, FileText, Package, Receipt, LogOut, Users, Settings, Menu, X } from 'lucide-react';
import { clsx } from 'clsx';

export default function Layout({ onLogout }: { onLogout: () => void }) {
  const location = useLocation();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const navItems = [
    { name: 'Dashboard', href: '/', icon: LayoutDashboard },
    { name: 'New Bill', href: '/new-bill', icon: Receipt },
    { name: 'Products', href: '/products', icon: Package },
    { name: 'Customers', href: '/customers', icon: Users },
    { name: 'Invoices', href: '/invoices', icon: FileText },
    { name: 'Settings', href: '/settings', icon: Settings },
  ];

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100 overflow-hidden">
      {/* Mobile menu overlay */}
      {isMobileMenuOpen && (
        <div 
          className="fixed inset-0 bg-zinc-950/80 backdrop-blur-sm z-40 lg:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div className={clsx(
        "fixed inset-y-0 left-0 z-50 w-64 bg-zinc-900 border-r border-zinc-800 flex flex-col transition-transform duration-300 ease-in-out lg:static lg:translate-x-0",
        isMobileMenuOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        <div className="h-16 flex items-center justify-between px-6 border-b border-zinc-800">
          <h1 className="text-xl font-black tracking-tight text-lime-400">Bill Express</h1>
          <button 
            className="lg:hidden text-zinc-400 hover:text-white"
            onClick={() => setIsMobileMenuOpen(false)}
            aria-label="Close menu"
            title="Close menu"
          >
            <X className="h-6 w-6" />
          </button>
        </div>
        
        <nav className="flex-1 px-4 py-6 space-y-2 overflow-y-auto">
          {navItems.map((item) => {
            const isActive = location.pathname === item.href;
            return (
              <Link
                key={item.name}
                to={item.href}
                onClick={() => setIsMobileMenuOpen(false)}
                className={clsx(
                  'flex items-center px-4 py-3 text-sm font-semibold rounded-xl transition-all duration-200',
                  isActive
                    ? 'bg-lime-400 text-zinc-950 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] translate-y-[-2px] translate-x-[-2px]'
                    : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100'
                )}
              >
                <item.icon
                  className={clsx(
                    'mr-3 shrink-0 h-5 w-5',
                    isActive ? 'text-zinc-950' : 'text-zinc-500 group-hover:text-zinc-300'
                  )}
                  aria-hidden="true"
                />
                {item.name}
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-zinc-800">
          <button onClick={onLogout} className="flex items-center w-full px-4 py-3 text-sm font-semibold text-zinc-400 rounded-xl hover:bg-zinc-800 hover:text-zinc-100 transition-colors">
            <LogOut className="mr-3 shrink-0 h-5 w-5 text-zinc-500" />
            Logout
          </button>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden bg-zinc-950 w-full">
        {/* Mobile Header */}
        <div className="lg:hidden h-16 flex items-center px-4 border-b border-zinc-800 bg-zinc-900">
          <button
            onClick={() => setIsMobileMenuOpen(true)}
            className="text-zinc-400 hover:text-white focus:outline-none"
            aria-label="Open menu"
            title="Open menu"
          >
            <Menu className="h-6 w-6" />
          </button>
          <h1 className="ml-4 text-xl font-black tracking-tight text-lime-400">Bill Express</h1>
        </div>
        
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
