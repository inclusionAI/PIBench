import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import Products from '../../src/pages/Products';
import * as apiModule from '../../src/utils/api.js';

vi.mock('../../src/utils/api.js', () => ({
  apiFetch: vi.fn(),
}));

describe('Products Component', () => {
  let alertMock: any;
  let consoleErrorMock: any;

  beforeEach(() => {
    vi.clearAllMocks();
    alertMock = vi.spyOn(window, 'alert').mockImplementation(() => {});
    consoleErrorMock = vi.spyOn(console, 'error').mockImplementation(() => {});

    // Mock initial fetch
    (apiModule.apiFetch as any).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve([]),
    });
  });

  afterEach(() => {
    alertMock.mockRestore();
    consoleErrorMock.mockRestore();
  });

  it('should handle API error when saving a product (non-ok response)', async () => {
    const user = userEvent.setup();
    render(<Products />);

    // Wait for initial fetch
    await waitFor(() => {
      expect(apiModule.apiFetch).toHaveBeenCalledWith('/api/products?page=1&limit=50&search=&category=All&sort=name_asc');
    });

    // Open add product modal
    await user.click(screen.getAllByText('Add Product')[0]);

    // Fill the required fields
    await user.type(screen.getByText(/Code\/SKU/i).nextElementSibling as HTMLElement, 'P001');
    await user.type(screen.getByText(/HSN Code/i).nextElementSibling as HTMLElement, '1234');
    await user.type(screen.getAllByText(/^Name$/i)[1].nextElementSibling as HTMLElement, 'Test Product');
    await user.type(screen.getAllByText(/Price \(ex GST\)/i)[1].nextElementSibling as HTMLElement, '100');
    // Stock is prefilled to 0, which is fine

    // Mock the POST request to return an error response
    (apiModule.apiFetch as any).mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ error: 'Duplicate code' }),
    });

    // Submit the form
    await user.click(screen.getByText('Save'));

    // Verify alert was called with the correct message
    await waitFor(() => {
      expect(alertMock).toHaveBeenCalledWith('Error: Duplicate code');
    });
  });

  it('should handle generic error when saving a product (network failure)', async () => {
    const user = userEvent.setup();
    render(<Products />);

    // Wait for initial fetch
    await waitFor(() => {
      expect(apiModule.apiFetch).toHaveBeenCalledWith('/api/products?page=1&limit=50&search=&category=All&sort=name_asc');
    });

    // Open add product modal
    await user.click(screen.getAllByText('Add Product')[0]);

    // Fill the required fields
    await user.type(screen.getByText(/Code\/SKU/i).nextElementSibling as HTMLElement, 'P002');
    await user.type(screen.getByText(/HSN Code/i).nextElementSibling as HTMLElement, '5678');
    await user.type(screen.getAllByText(/^Name$/i)[1].nextElementSibling as HTMLElement, 'Test Product 2');
    await user.type(screen.getAllByText(/Price \(ex GST\)/i)[1].nextElementSibling as HTMLElement, '200');

    // Mock the POST request to throw a network error
    (apiModule.apiFetch as any).mockRejectedValueOnce(new Error('Network error'));

    // Submit the form
    await user.click(screen.getByText('Save'));

    // Verify console.error and alert were called
    await waitFor(() => {
      expect(consoleErrorMock).toHaveBeenCalled();
      expect(alertMock).toHaveBeenCalledWith('An error occurred while saving the product.');
    });
  });
});
