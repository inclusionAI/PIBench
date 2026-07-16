import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import InventoryAdjustmentModal from '../../src/components/InventoryAdjustmentModal';
import * as api from '../../src/utils/api';
import { Product } from '../../src/types';

vi.mock('../../src/utils/api', () => ({
  apiFetch: vi.fn(),
}));

describe('InventoryAdjustmentModal', () => {
  const mockProduct: Product = {
    id: 1,
    code: 'P001',
    name: 'Test Product',
    category: 'Fertilizer',
    unit: 'Bag',
    price_ex_gst: 100,
    gst_rate: 18,
    hsn_code: '1234',
    stock: 50
  };

  const mockOnClose = vi.fn();
  const mockOnSuccess = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders correctly in adjust tab', () => {
    render(
      <InventoryAdjustmentModal
        product={mockProduct}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />
    );

    expect(screen.getByText('Test Product')).toBeDefined();
    expect(screen.getByText(/Current Stock:/i)).toBeDefined();
    expect(screen.getByLabelText(/Adjustment Type/i)).toBeDefined();
    expect(screen.getByPlaceholderText(/Enter amount.../i)).toBeDefined();
  });

  it('switches to history tab and fetches transactions', async () => {
    const mockTransactions = [
      { id: 1, type: 'restock', quantity: 10, reason: 'Initial', date: '2026-04-17T12:00:00Z' }
    ];
    (api.apiFetch as any).mockResolvedValue({
      json: () => Promise.resolve(mockTransactions),
    });

    render(
      <InventoryAdjustmentModal
        product={mockProduct}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />
    );

    const historyTab = screen.getByRole('button', { name: /History/i });
    fireEvent.click(historyTab);

    expect(api.apiFetch).toHaveBeenCalledWith('/api/products/1/transactions');
    await waitFor(() => {
      expect(screen.getByText('restock')).toBeDefined();
      expect(screen.getByText('+10')).toBeDefined();
      expect(screen.getByText('Initial')).toBeDefined();
    });
  });

  it('submits stock adjustment successfully', async () => {
    (api.apiFetch as any).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true }),
    });

    render(
      <InventoryAdjustmentModal
        product={mockProduct}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />
    );

    fireEvent.change(screen.getByPlaceholderText(/Enter amount.../i), { target: { value: '20' } });
    fireEvent.change(screen.getByPlaceholderText(/Why is this adjustment being made?/i), { target: { value: 'Refill' } });
    
    const submitButton = screen.getByRole('button', { name: /Save Adjustment/i });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(api.apiFetch).toHaveBeenCalledWith('/api/products/1/stock-adjustment', expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          type: 'restock',
          quantity: 20,
          reason: 'Refill'
        })
      }));
      expect(mockOnSuccess).toHaveBeenCalled();
      expect(mockOnClose).toHaveBeenCalled();
    });
  });
});
