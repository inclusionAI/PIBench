import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from '../../src/pages/Dashboard';
import * as api from '../../src/utils/api';

vi.mock('../../src/utils/api', () => ({
  apiFetch: vi.fn(),
}));

describe('Dashboard Page', () => {
  const mockAnalytics = {
    todaySales: 1500,
    todayInvoices: 5,
    totalProducts: 50,
    totalCustomers: 20,
    last7Days: [{ day: '2026-04-17', sales: 1500 }],
    topProducts: [{ name: 'Product A', qty: 10, revenue: 1000 }],
    lowStock: [
      { id: 1, name: 'Low Stock Item', code: 'LS001', stock: 5, unit: 'pcs' }
    ]
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders dashboard stats correctly', async () => {
    (api.apiFetch as any).mockResolvedValue({
      json: () => Promise.resolve(mockAnalytics),
    });

    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('₹1500.00')).toBeDefined();
      // Use getAllByText and check for specific context or count
      const invoiceCountElements = screen.getAllByText('5');
      expect(invoiceCountElements.length).toBeGreaterThanOrEqual(1);
      
      expect(screen.getByText('50')).toBeDefined();
      expect(screen.getByText('20')).toBeDefined();
    });
  });

  it('renders low stock alerts when data is present', async () => {
    (api.apiFetch as any).mockResolvedValue({
      json: () => Promise.resolve(mockAnalytics),
    });

    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Low Stock Alerts')).toBeDefined();
      expect(screen.getByText('Low Stock Item')).toBeDefined();
      
      // The stock value '5' appears in the alert
      const stockValueElements = screen.getAllByText('5');
      expect(stockValueElements.some(el => el.classList.contains('text-rose-500'))).toBe(true);
    });
  });

  it('does not render low stock alerts when no items are low on stock', async () => {
    (api.apiFetch as any).mockResolvedValue({
      json: () => Promise.resolve({ ...mockAnalytics, lowStock: [] }),
    });

    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.queryByText('Low Stock Alerts')).toBeNull();
    });
  });
});
