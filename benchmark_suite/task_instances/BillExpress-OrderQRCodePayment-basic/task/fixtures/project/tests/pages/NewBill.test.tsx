import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import NewBill from '../../src/pages/NewBill';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const mockProducts = [
  {
    id: 1,
    name: 'Test Product 1',
    code: 'TP1',
    hsn_code: '1234',
    unit: 'pcs',
    price_ex_gst: 100,
    gst_rate: 18,
    category: 'Test Category',
  },
  {
    id: 2,
    name: 'Test Product 2',
    code: 'TP2',
    hsn_code: '5678',
    unit: 'pcs',
    price_ex_gst: 200,
    gst_rate: 12,
    category: 'Test Category',
  }
];

describe('NewBill Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn().mockImplementation((url) => {
      if (url.startsWith('/api/products')) {
        return Promise.resolve({
          json: () => Promise.resolve({ data: mockProducts, total: mockProducts.length }),
        });
      }
      return Promise.resolve({
        json: () => Promise.resolve({ success: true }),
      });
    });
  });

  const renderComponent = () => {
    return render(
      <BrowserRouter>
        <NewBill />
      </BrowserRouter>
    );
  };

  it('should render the component correctly', async () => {
    renderComponent();

    expect(screen.getByText('Create New Bill')).toBeInTheDocument();
    expect(screen.getByText('Customer Details')).toBeInTheDocument();
    expect(screen.getByText('Subtotal (excl. GST)')).toBeInTheDocument();
    expect(screen.getByText('Grand Total')).toBeInTheDocument();
  });

  it('should add an item and verify subtotal and grandTotal math', async () => {
    const user = userEvent.setup();
    renderComponent();

    // Search for a product
    const searchInput = screen.getByPlaceholderText('Search by name or code...');
    await user.type(searchInput, 'Test');

    // Wait for filtered products to show up
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/products?search=Test'), expect.any(Object));
      expect(screen.getByText('Test Product 1')).toBeInTheDocument();
    });

    // Add item 1
    await user.click(screen.getByText('Test Product 1'));

    // Check Subtotal: 100 (price_ex_gst)
    expect(screen.getByText('Subtotal (excl. GST)')).toBeInTheDocument();
    expect(screen.getAllByText('₹100.00').length).toBeGreaterThan(0);

    // Check CGST and SGST: 9 each (18% of 100)
    expect(screen.getAllByText('₹9.00').length).toBeGreaterThan(0);

    // Check Grand Total: 100 + 9 + 9 = 118
    expect(screen.getByText('₹118.00', { selector: 'span.text-lime-400' })).toBeInTheDocument();

    // Update quantity by searching for the item and clicking it again
    const searchInputAgain = screen.getByPlaceholderText('Search by name or code...');
    await user.clear(searchInputAgain);
    await user.type(searchInputAgain, 'Test Product 1');
    await waitFor(() => {
      // One might be in the cart, so we expect at least 2 or we can just find the list item
      const elements = screen.getAllByText('Test Product 1');
      expect(elements.length).toBeGreaterThan(0);

      // Look for the specific li element in the dropdown
      const listItem = elements.find(el => el.closest('li'));
      expect(listItem).toBeTruthy();
    });
    // Find the add item option
    const elements = screen.getAllByText('Test Product 1');
    const addProduct1 = elements.find(el => el.closest('li')) || elements[0];
    await user.click(addProduct1);

    // We need to wait for the UI to update
    await waitFor(() => {
      expect(screen.getAllByText('₹200.00').length).toBeGreaterThan(0);
    });

    // Check new CGST and SGST
    expect(screen.getAllByText('₹18.00').length).toBeGreaterThan(0);

    // Check new Grand Total: 200 + 18 + 18 = 236
    await waitFor(() => {
      const el = screen.getAllByText(/236\.00/);
      expect(el.length).toBeGreaterThan(0);
    });
  });

  it('should apply discount correctly and update grandTotal', async () => {
    const user = userEvent.setup();
    renderComponent();

    // Search for a product
    const searchInput = screen.getByPlaceholderText('Search by name or code...');
    await user.type(searchInput, 'Test');

    // Add item 1
    await waitFor(() => {
      expect(screen.getByText('Test Product 1')).toBeInTheDocument();
    });
    await user.click(screen.getByText('Test Product 1'));

    // Initial Grand Total: 118
    expect(screen.getByText('₹118.00', { selector: 'span.text-lime-400' })).toBeInTheDocument();

    // Apply value discount of 18
    const discountInputs = screen.getAllByRole('spinbutton');
    // Discount input is the one with min="0" and no step attribute (or step implicitly 1), Amount Paid has step="0.01"
    const discountInput = discountInputs.find(input => (input as HTMLInputElement).className.includes('w-24'));

    if (discountInput) {
      await user.clear(discountInput);
      await user.type(discountInput, '18');
    }

    // New Grand Total: 118 - 18 = 100
    expect(screen.getByText('₹100.00', { selector: 'span.text-lime-400' })).toBeInTheDocument();

    // Change discount type to percentage
    const discountTypeSelect = screen.getByRole('combobox');
    await user.selectOptions(discountTypeSelect, 'percentage');

    // Apply percentage discount of 10%
    if (discountInput) {
      await user.clear(discountInput);
      await user.type(discountInput, '10');
    }

    // New Grand Total: 118 - (118 * 0.1) = 118 - 11.8 = 106.2
    expect(screen.getByText('₹106.20', { selector: 'span.text-lime-400' })).toBeInTheDocument();
  });

  it('should show an alert when API returns success: false on save', async () => {
    const user = userEvent.setup();
    const alertMock = vi.spyOn(window, 'alert').mockImplementation(() => {});

    renderComponent();

    // Add item 1
    const searchInput = screen.getByPlaceholderText('Search by name or code...');
    await user.type(searchInput, 'Test');
    await waitFor(() => {
      expect(screen.getByText('Test Product 1')).toBeInTheDocument();
    });
    await user.click(screen.getByText('Test Product 1'));

    // Mock fetch for the save operation
    global.fetch = vi.fn().mockImplementation((url) => {
      if (url === '/api/invoices') {
        return Promise.resolve({
          json: () => Promise.resolve({ success: false, error: 'Database error' }),
        });
      }
      if (url.startsWith('/api/products')) {
        return Promise.resolve({
          json: () => Promise.resolve({ data: mockProducts, total: mockProducts.length }),
        });
      }
      return Promise.resolve({
        json: () => Promise.resolve({}),
      });
    });

    const saveButton = screen.getByText('Save & Generate Invoice');
    await user.click(saveButton);

    await waitFor(() => {
      expect(alertMock).toHaveBeenCalledWith('Database error');
    });

    alertMock.mockRestore();
  });

  it('should show an alert and log error when API fetch throws an error on save', async () => {
    const user = userEvent.setup();
    const alertMock = vi.spyOn(window, 'alert').mockImplementation(() => {});
    const consoleErrorMock = vi.spyOn(console, 'error').mockImplementation(() => {});

    renderComponent();

    // Add item 1
    const searchInput = screen.getByPlaceholderText('Search by name or code...');
    await user.type(searchInput, 'Test');
    await waitFor(() => {
      expect(screen.getByText('Test Product 1')).toBeInTheDocument();
    });
    await user.click(screen.getByText('Test Product 1'));

    // Mock fetch for the save operation to throw an error
    global.fetch = vi.fn().mockImplementation((url) => {
      if (url === '/api/invoices') {
        return Promise.reject(new Error('Network failure'));
      }
      if (url.startsWith('/api/products')) {
        return Promise.resolve({
          json: () => Promise.resolve({ data: mockProducts, total: mockProducts.length }),
        });
      }
      return Promise.resolve({
        json: () => Promise.resolve({}),
      });
    });

    const saveButton = screen.getByText('Save & Generate Invoice');
    await user.click(saveButton);

    await waitFor(() => {
      expect(consoleErrorMock).toHaveBeenCalledWith(expect.any(Error));
      expect(alertMock).toHaveBeenCalledWith('Failed to save invoice');
    });

    alertMock.mockRestore();
    consoleErrorMock.mockRestore();
  });
});
