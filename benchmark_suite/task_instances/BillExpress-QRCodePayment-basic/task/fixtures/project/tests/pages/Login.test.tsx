import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import Login from '../../src/pages/Login';

describe('Login Component', () => {
  const mockOnLogin = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();

    // Default fetch mock (success)
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });
  });

  const renderComponent = () => {
    return render(<Login onLogin={mockOnLogin} />);
  };

  it('renders the login form correctly', () => {
    renderComponent();

    expect(screen.getByText('Bill Express')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Enter username')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Enter password')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  it('handles successful login', async () => {
    const user = userEvent.setup();
    renderComponent();

    const usernameInput = screen.getByPlaceholderText('Enter username');
    const passwordInput = screen.getByPlaceholderText('Enter password');
    const submitButton = screen.getByRole('button', { name: /sign in/i });

    await user.type(usernameInput, 'admin');
    await user.type(passwordInput, 'admin123');
    await user.click(submitButton);

    const expectedCredentials = btoa('admin:admin123');

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith('/api/login', {
        headers: {
          'Authorization': `Basic ${expectedCredentials}`
        }
      });
    });

    expect(localStorage.getItem('auth_credentials')).toBe(expectedCredentials);
    expect(mockOnLogin).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/invalid username or password/i)).not.toBeInTheDocument();
  });

  it('handles invalid credentials', async () => {
    // Override fetch mock for failure
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({}),
    });

    const user = userEvent.setup();
    renderComponent();

    const usernameInput = screen.getByPlaceholderText('Enter username');
    const passwordInput = screen.getByPlaceholderText('Enter password');
    const submitButton = screen.getByRole('button', { name: /sign in/i });

    await user.type(usernameInput, 'wronguser');
    await user.type(passwordInput, 'wrongpass');
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText('Invalid username or password')).toBeInTheDocument();
    });

    expect(localStorage.getItem('auth_credentials')).toBeNull();
    expect(mockOnLogin).not.toHaveBeenCalled();
  });

  it('clears existing error message on subsequent submit', async () => {
    // Override fetch mock for failure first
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({}),
    }).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({}),
    });

    const user = userEvent.setup();
    renderComponent();

    const usernameInput = screen.getByPlaceholderText('Enter username');
    const passwordInput = screen.getByPlaceholderText('Enter password');
    const submitButton = screen.getByRole('button', { name: /sign in/i });

    // First attempt: Invalid credentials
    await user.type(usernameInput, 'wronguser');
    await user.type(passwordInput, 'wrongpass');
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText('Invalid username or password')).toBeInTheDocument();
    });

    // Second attempt: Valid credentials
    await user.clear(usernameInput);
    await user.clear(passwordInput);
    await user.type(usernameInput, 'admin');
    await user.type(passwordInput, 'admin123');
    await user.click(submitButton);

    // Error message should disappear immediately upon clicking submit
    await waitFor(() => {
      expect(screen.queryByText('Invalid username or password')).not.toBeInTheDocument();
    });

    // And then onLogin should be called
    await waitFor(() => {
      expect(mockOnLogin).toHaveBeenCalledTimes(1);
    });
  });

  it('handles network error during login', async () => {
    // Override fetch mock to throw error
    global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

    const user = userEvent.setup();
    renderComponent();

    const usernameInput = screen.getByPlaceholderText('Enter username');
    const passwordInput = screen.getByPlaceholderText('Enter password');
    const submitButton = screen.getByRole('button', { name: /sign in/i });

    await user.type(usernameInput, 'admin');
    await user.type(passwordInput, 'admin123');
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText('An error occurred while signing in')).toBeInTheDocument();
    });

    expect(localStorage.getItem('auth_credentials')).toBeNull();
    expect(mockOnLogin).not.toHaveBeenCalled();
  });
});
