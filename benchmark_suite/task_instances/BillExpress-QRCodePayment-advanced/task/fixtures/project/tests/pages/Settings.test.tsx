import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import Settings from '../../src/pages/Settings';
import { apiFetch } from '../../src/utils/api.js';

// Mock apiFetch
vi.mock('../../src/utils/api.js', () => ({
  apiFetch: vi.fn()
}));

const mockSettings = {
  store_name: 'My Store',
  address: '123 Main St',
  phone: '1234567890',
  gstin: '22AAAAA0000A1Z5',
  state_code: '22',
  logo_url: 'http://example.com/logo.png'
};

describe('Settings Component', () => {
  let consoleErrorSpy: any;
  let alertSpy: any;

  beforeEach(() => {
    vi.clearAllMocks();
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
    alertSpy.mockRestore();
  });

  it('should fetch and display settings on mount', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      json: () => Promise.resolve(mockSettings)
    } as Response);

    render(<Settings />);

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/api/settings');
    });

    await waitFor(() => {
      expect(screen.getByDisplayValue('My Store')).toBeInTheDocument();
      expect(screen.getByDisplayValue('123 Main St')).toBeInTheDocument();
      expect(screen.getByDisplayValue('1234567890')).toBeInTheDocument();
      expect(screen.getByDisplayValue('22AAAAA0000A1Z5')).toBeInTheDocument();
      expect(screen.getByDisplayValue('22')).toBeInTheDocument();
      expect(screen.getByDisplayValue('http://example.com/logo.png')).toBeInTheDocument();
    });
  });

  it('should save settings successfully and alert', async () => {
    const user = userEvent.setup();

    // Initial fetch
    vi.mocked(apiFetch).mockResolvedValueOnce({
      json: () => Promise.resolve(mockSettings)
    } as Response);

    render(<Settings />);

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/api/settings');
    });

    // Setup for save
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ success: true })
    } as Response);

    const saveBtn = screen.getByRole('button', { name: /save settings/i });
    await user.click(saveBtn);

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/api/settings', expect.objectContaining({
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mockSettings)
      }));
    });

    expect(alertSpy).toHaveBeenCalledWith('Settings saved successfully!');
  });

  it('should update input values and save updated settings', async () => {
    const user = userEvent.setup();

    // Initial fetch with empty settings
    vi.mocked(apiFetch).mockResolvedValueOnce({
      json: () => Promise.resolve({
        store_name: '',
        address: '',
        phone: '',
        gstin: '',
        state_code: '',
        logo_url: ''
      })
    } as Response);

    render(<Settings />);

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/api/settings');
    });

    // Type into inputs
    const storeNameInput = screen.getByText('Store Name').nextElementSibling as HTMLInputElement;
    const addressInput = screen.getByText('Address').nextElementSibling as HTMLTextAreaElement;
    const phoneInput = screen.getByText('Phone').nextElementSibling as HTMLInputElement;
    const gstinInput = screen.getByText('GSTIN').nextElementSibling as HTMLInputElement;
    const stateCodeInput = screen.getByText('State Code').nextElementSibling as HTMLInputElement;
    const logoUrlInput = screen.getByText('Logo URL (Optional)').nextElementSibling as HTMLInputElement;

    await user.type(storeNameInput, 'New Store');
    await user.type(addressInput, '456 New St');
    await user.type(phoneInput, '0987654321');
    await user.type(gstinInput, '33BBBBB0000B2Z6');
    await user.type(stateCodeInput, '33');
    await user.type(logoUrlInput, 'http://example.com/newlogo.png');

    // Setup for save
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ success: true })
    } as Response);

    const saveBtn = screen.getByRole('button', { name: /save settings/i });
    await user.click(saveBtn);

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/api/settings', expect.objectContaining({
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          store_name: 'New Store',
          address: '456 New St',
          phone: '0987654321',
          gstin: '33BBBBB0000B2Z6',
          state_code: '33',
          logo_url: 'http://example.com/newlogo.png'
        })
      }));
    });

    expect(alertSpy).toHaveBeenCalledWith('Settings saved successfully!');
  });

  it('should catch error when saving settings fails and alert', async () => {
    const user = userEvent.setup();

    // Initial fetch
    vi.mocked(apiFetch).mockResolvedValueOnce({
      json: () => Promise.resolve(mockSettings)
    } as Response);

    render(<Settings />);

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/api/settings');
    });

    // Mock API to reject for the save call
    const testError = new Error('Network error');
    vi.mocked(apiFetch).mockRejectedValueOnce(testError);

    const saveBtn = screen.getByRole('button', { name: /save settings/i });
    await user.click(saveBtn);

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/api/settings', expect.objectContaining({
        method: 'PUT'
      }));
    });

    expect(consoleErrorSpy).toHaveBeenCalledWith(testError);
    expect(alertSpy).toHaveBeenCalledWith('Failed to save settings');
  });
});
