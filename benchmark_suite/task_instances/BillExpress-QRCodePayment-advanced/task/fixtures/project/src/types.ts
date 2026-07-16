export interface Product {
  id: number;
  code: string;
  name: string;
  category: string;
  unit: string;
  price_ex_gst: number;
  gst_rate: number;
  hsn_code: string;
  stock: number;
}

export interface Customer {
  id: number;
  name: string;
  mobile?: string;
  address?: string;
  gstin?: string;
  state?: string;
  lifetime_value: number;
}

export interface InvoiceItem {
  id: number;
  product_id: number;
  product_name: string;
  product_code: string;
  hsn_code: string;
  unit: string;
  quantity: number;
  price_ex_gst: number;
  gst_rate: number;
  cgst_amount: number;
  sgst_amount: number;
  igst_amount?: number;
  total: number;
}

export interface Invoice {
  id: number;
  invoice_number: string;
  date: string;
  customer_id?: number;
  customer_name?: string;
  customer_mobile?: string;
  customer_address?: string;
  customer_gstin?: string;
  customer_state?: string;
  type: string;
  subtotal: number;
  discount: number;
  cgst_total: number;
  sgst_total: number;
  igst_total: number;
  grand_total: number;
  status: string;
  payment_status: string;
  amount_paid: number;
  items: InvoiceItem[];
}

export interface AnalyticsData {
  last7Days: { day: string; sales: number }[];
  topProducts: { name: string; qty: number }[];
  lowStock: Product[];
}

export interface DashboardStats {
  todaySales: number;
  todayInvoices: number;
  totalProducts: number;
  totalCustomers: number;
}

export interface Settings {
  store_name: string;
  address: string;
  phone: string;
  gstin: string;
  state_code: string;
  logo_url?: string;
}
