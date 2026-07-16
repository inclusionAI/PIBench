import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import App from '../src/App';

vi.mock('../src/components/Layout', () => ({
  default: ({ onLogout }: { onLogout: () => void }) => {
    const { Outlet } = require('react-router-dom');
    return (
      <div data-testid="layout">
        <button onClick={onLogout}>Mock Logout Button</button>
        <Outlet />
      </div>
    );
  }
}));

vi.mock('../src/pages/Dashboard', () => ({ default: () => <div data-testid="dashboard-page" /> }));
vi.mock('../src/pages/NewBill', () => ({ default: () => <div data-testid="new-bill-page" /> }));
vi.mock('../src/pages/Products', () => ({ default: () => <div data-testid="products-page" /> }));
vi.mock('../src/pages/Customers', () => ({ default: () => <div data-testid="customers-page" /> }));
vi.mock('../src/pages/Invoices', () => ({ default: () => <div data-testid="invoices-page" /> }));
vi.mock('../src/pages/InvoiceView', () => ({ default: () => <div data-testid="invoice-view-page" /> }));
vi.mock('../src/pages/Settings', () => ({ default: () => <div data-testid="settings-page" /> }));
vi.mock('../src/pages/Login', () => ({
  default: ({ onLogin }: { onLogin: () => void }) => (
    <div data-testid="login-page">
      <button onClick={onLogin}>Mock Login Button</button>
    </div>
  )
}));

describe('App Component', () => {
  beforeEach(() => {
    localStorage.clear();
    window.history.pushState({}, 'Test', '/');
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders Login when not authenticated', () => {
    render(<App />);
    expect(screen.getByTestId('login-page')).toBeInTheDocument();
    expect(screen.queryByTestId('layout')).not.toBeInTheDocument();
  });

  it('renders Layout and Dashboard when authenticated', async () => {
    localStorage.setItem('isAuthenticated', 'true');
    render(<App />);
    expect(await screen.findByTestId('layout')).toBeInTheDocument();
    expect(await screen.findByTestId('dashboard-page')).toBeInTheDocument();
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument();
  });

  it('updates state and localStorage on login', async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(screen.getByTestId('login-page')).toBeInTheDocument();

    await user.click(screen.getByText('Mock Login Button'));

    expect(localStorage.getItem('isAuthenticated')).toBe('true');
    expect(await screen.findByTestId('layout')).toBeInTheDocument();
  });

  it('updates state and localStorage on logout', async () => {
    localStorage.setItem('isAuthenticated', 'true');
    localStorage.setItem('auth_credentials', 'fake_creds');

    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByTestId('layout')).toBeInTheDocument();

    await user.click(screen.getByText('Mock Logout Button'));

    expect(localStorage.getItem('isAuthenticated')).toBe('false');
    expect(localStorage.getItem('auth_credentials')).toBeNull();
    expect(screen.getByTestId('login-page')).toBeInTheDocument();
  });

  it('handles routing correctly when authenticated', async () => {
    localStorage.setItem('isAuthenticated', 'true');
    window.history.pushState({}, 'Test', '/products');

    render(<App />);

    expect(await screen.findByTestId('layout')).toBeInTheDocument();
    expect(await screen.findByTestId('products-page')).toBeInTheDocument();
  });

  it('redirects unknown routes to dashboard', async () => {
    localStorage.setItem('isAuthenticated', 'true');
    window.history.pushState({}, 'Test', '/unknown-route');

    render(<App />);

    expect(await screen.findByTestId('layout')).toBeInTheDocument();
    expect(await screen.findByTestId('dashboard-page')).toBeInTheDocument();
  });
});
