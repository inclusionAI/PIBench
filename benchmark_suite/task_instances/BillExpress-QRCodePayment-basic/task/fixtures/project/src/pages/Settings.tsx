import React, { useState, useEffect } from 'react';
import { Save, Loader2 } from 'lucide-react';
import { apiFetch } from '../utils/api.js';

export default function Settings() {
  const [settings, setSettings] = useState({
    store_name: '',
    address: '',
    phone: '',
    gstin: '',
    state_code: '',
    logo_url: '',
    low_stock_threshold: 10
  });
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    apiFetch('/api/settings')
      .then(res => res.json())
      .then(data => {
        if (data) setSettings(data);
      });
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      await apiFetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
      });
      alert('Settings saved successfully!');
    } catch (err) {
      console.error(err);
      alert('Failed to save settings');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-black tracking-tight text-white">Store Settings</h1>
      </div>

      <div className="bg-zinc-900 border-2 border-zinc-800 rounded-2xl p-8">
        <form onSubmit={handleSave} className="space-y-6">
          <div>
            <label htmlFor="store_name" className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">Store Name</label>
            <input
              id="store_name"
              type="text"
              value={settings.store_name}
              onChange={(e) => setSettings({ ...settings, store_name: e.target.value })}
              className="block w-full bg-zinc-950 border-2 border-zinc-800 rounded-xl px-4 py-3 text-white focus:ring-0 focus:border-lime-400 transition-colors font-bold disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isSaving}
              required
            />
          </div>

          <div>
            <label htmlFor="address" className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">Address</label>
            <textarea
              id="address"
              value={settings.address}
              onChange={(e) => setSettings({ ...settings, address: e.target.value })}
              rows={3}
              className="block w-full bg-zinc-950 border-2 border-zinc-800 rounded-xl px-4 py-3 text-white focus:ring-0 focus:border-lime-400 transition-colors font-bold disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isSaving}
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-6">
            <div>
              <label htmlFor="phone" className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">Phone</label>
              <input
                id="phone"
                type="text"
                value={settings.phone}
                onChange={(e) => setSettings({ ...settings, phone: e.target.value })}
                className="block w-full bg-zinc-950 border-2 border-zinc-800 rounded-xl px-4 py-3 text-white focus:ring-0 focus:border-lime-400 transition-colors font-bold disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={isSaving}
                required
              />
            </div>
            <div>
              <label htmlFor="gstin" className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">GSTIN</label>
              <input
                id="gstin"
                type="text"
                value={settings.gstin}
                onChange={(e) => setSettings({ ...settings, gstin: e.target.value })}
                className="block w-full bg-zinc-950 border-2 border-zinc-800 rounded-xl px-4 py-3 text-white focus:ring-0 focus:border-lime-400 transition-colors font-bold disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={isSaving}
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-6">
            <div>
              <label htmlFor="state_code" className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">State Code</label>
              <input
                id="state_code"
                type="text"
                value={settings.state_code}
                onChange={(e) => setSettings({ ...settings, state_code: e.target.value })}
                className="block w-full bg-zinc-950 border-2 border-zinc-800 rounded-xl px-4 py-3 text-white focus:ring-0 focus:border-lime-400 transition-colors font-bold disabled:opacity-50 disabled:cursor-not-allowed"
                placeholder="e.g. 19 (West Bengal)"
                disabled={isSaving}
                required
              />
            </div>
            <div>
              <label htmlFor="low_stock_threshold" className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">Low Stock Threshold</label>
              <input
                id="low_stock_threshold"
                type="number"
                value={settings.low_stock_threshold}
                onChange={(e) => setSettings({ ...settings, low_stock_threshold: parseInt(e.target.value) || 0 })}
                className="block w-full bg-zinc-950 border-2 border-zinc-800 rounded-xl px-4 py-3 text-white focus:ring-0 focus:border-lime-400 transition-colors font-bold disabled:opacity-50 disabled:cursor-not-allowed"
                placeholder="e.g. 10"
                disabled={isSaving}
                min="0"
                required
              />
            </div>
          </div>

          <div>
            <label htmlFor="logo_url" className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2">Logo URL (Optional)</label>
            <input
              id="logo_url"
              type="text"
              value={settings.logo_url || ''}
              onChange={(e) => setSettings({ ...settings, logo_url: e.target.value })}
              className="block w-full bg-zinc-950 border-2 border-zinc-800 rounded-xl px-4 py-3 text-white focus:ring-0 focus:border-lime-400 transition-colors font-bold disabled:opacity-50 disabled:cursor-not-allowed"
              placeholder="https://..."
              disabled={isSaving}
            />
          </div>

          <div className="pt-6 border-t-2 border-zinc-800">
            <button
              type="submit"
              disabled={isSaving}
              className="w-full flex justify-center items-center py-4 px-4 border-2 border-zinc-950 rounded-xl shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] text-lg font-black text-zinc-950 bg-lime-400 hover:bg-lime-300 hover:translate-y-[-2px] hover:translate-x-[-2px] hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:hover:translate-x-0 disabled:hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] transition-all uppercase tracking-wider"
            >
              {isSaving ? (
                <>
                  <Loader2 className="animate-spin -ml-1 mr-2 h-5 w-5" />
                  Saving...
                </>
              ) : (
                <>
                  <Save className="-ml-1 mr-2 h-5 w-5" />
                  Save Settings
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
