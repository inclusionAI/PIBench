import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Barcode, CheckCircle2, Loader2, RefreshCw } from 'lucide-react';
import { apiFetch } from '../utils/api.js';

type InvoiceSummary = {
  id: number;
  invoice_number: string;
  customer_name?: string;
  grand_total: number;
  payment_status: string;
  amount_paid: number;
};

type BarcodePayment = {
  id: number;
  invoice_id: number;
  out_trade_no: string;
  auth_code_last4: string;
  scene: string;
  total_amount: number;
  trade_no?: string;
  trade_status: string;
  buyer_user_id?: string;
  buyer_logon_id?: string;
  retry_count: number;
  last_query_status?: string;
  paid_at?: string;
  invoice_number?: string;
  payment_status?: string;
  amount_paid?: number;
  grand_total?: number;
};

export default function AlipayBarcodePayment() {
  const { invoiceId } = useParams();
  const [invoice, setInvoice] = useState<InvoiceSummary | null>(null);
  const [payment, setPayment] = useState<BarcodePayment | null>(null);
  const [authCode, setAuthCode] = useState('286888888888888888');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [querying, setQuerying] = useState(false);
  const [error, setError] = useState('');

  const loadState = async () => {
    if (!invoiceId) return;
    try {
      const invoiceRes = await apiFetch(`/api/invoices/${invoiceId}`);
      const invoiceData = await invoiceRes.json();
      if (invoiceRes.ok) {
        setInvoice(invoiceData);
      }

      const paymentRes = await apiFetch(`/api/invoices/${invoiceId}/alipay/barcode/payment`);
      if (paymentRes.ok) {
        const paymentData = await paymentRes.json();
        setPayment(paymentData.payment);
      }
    } catch (err) {
      setError('Failed to load payment state');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadState();
  }, [invoiceId]);

  const submitPayment = async () => {
    if (!invoiceId) return;
    setSubmitting(true);
    setError('');

    try {
      const res = await apiFetch(`/api/invoices/${invoiceId}/alipay/barcode/pay`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auth_code: authCode })
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        setError(data.error || 'Barcode payment failed');
      } else {
        setPayment(data.payment);
      }
      await loadState();
    } catch (err) {
      setError('Barcode payment failed');
    } finally {
      setSubmitting(false);
    }
  };

  const queryPayment = async () => {
    if (!invoiceId) return;
    setQuerying(true);
    setError('');
    try {
      const res = await apiFetch(`/api/invoices/${invoiceId}/alipay/barcode/query`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok || !data.success) {
        setError(data.error || 'Barcode query failed');
      } else {
        setPayment(data.payment);
      }
      await loadState();
    } catch (err) {
      setError('Barcode query failed');
    } finally {
      setQuerying(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center text-zinc-400">
        <Loader2 className="h-8 w-8 animate-spin mr-3" />
        Loading barcode payment...
      </div>
    );
  }

  const paid = invoice?.payment_status === 'Paid' || payment?.trade_status === 'TRADE_SUCCESS';

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <Link to="/invoices" className="inline-flex items-center text-sm font-bold text-zinc-400 hover:text-white">
          <ArrowLeft className="mr-2 h-5 w-5" />
          Back to Invoices
        </Link>
        <button
          onClick={loadState}
          className="inline-flex items-center px-4 py-2 rounded-xl border-2 border-zinc-800 text-zinc-300 hover:text-white hover:border-lime-400"
        >
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </button>
      </div>

      <div className="bg-zinc-900 border-2 border-zinc-800 rounded-3xl p-8">
        <div className="flex items-start justify-between gap-6 border-b-2 border-zinc-800 pb-6 mb-8">
          <div>
            <p className="text-sm font-black uppercase tracking-wider text-lime-400 mb-2">Alipay Barcode Pay</p>
            <h1 className="text-3xl font-black text-white">{invoice?.invoice_number || `Invoice ${invoiceId}`}</h1>
            <p className="text-zinc-400 mt-2">{invoice?.customer_name || 'Walk-in customer'}</p>
          </div>
          <div className="text-right">
            <p className="text-sm font-black uppercase tracking-wider text-zinc-500">Amount</p>
            <p className="text-4xl font-black text-white">₹{Number(invoice?.grand_total || 0).toFixed(2)}</p>
            <span className={`inline-flex mt-3 px-3 py-1 rounded-full text-xs font-black uppercase ${paid ? 'bg-lime-400 text-zinc-950' : 'bg-amber-400 text-zinc-950'}`}>
              {paid ? 'Paid' : invoice?.payment_status || 'Unpaid'}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <div className="bg-zinc-950 rounded-2xl p-6 border-2 border-zinc-800">
            <div className="flex items-center mb-5">
              <Barcode className="h-6 w-6 mr-2 text-lime-400" />
              <h2 className="font-black uppercase tracking-wider text-white">Cashier Scan/Input</h2>
            </div>

            <label className="block text-sm font-black uppercase tracking-wider text-zinc-500 mb-2">
              Customer Alipay Auth Code
            </label>
            <input
              value={authCode}
              onChange={(event) => setAuthCode(event.target.value)}
              className="w-full bg-zinc-900 border-2 border-zinc-800 rounded-xl px-4 py-3 text-white font-mono focus:border-lime-400 focus:ring-0"
              placeholder="Enter barcode auth_code"
            />

            {error && (
              <div className="mt-5 bg-rose-500/10 border-2 border-rose-500 rounded-xl p-4 text-rose-300 font-bold">
                {error}
              </div>
            )}

            <button
              onClick={submitPayment}
              disabled={submitting || paid}
              className="mt-8 w-full flex justify-center items-center py-4 px-4 border-2 border-zinc-950 rounded-xl shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] text-lg font-black text-zinc-950 bg-lime-400 hover:bg-lime-300 disabled:opacity-50 disabled:cursor-not-allowed uppercase tracking-wider"
            >
              {paid ? (
                <>
                  <CheckCircle2 className="h-6 w-6 mr-2" />
                  Payment Complete
                </>
              ) : submitting ? (
                <>
                  <Loader2 className="h-6 w-6 mr-2 animate-spin" />
                  Processing...
                </>
              ) : (
                'Submit Barcode Payment'
              )}
            </button>
            <button
              onClick={queryPayment}
              disabled={querying || !payment || paid}
              className="mt-4 w-full flex justify-center items-center py-3 px-4 border-2 border-zinc-800 rounded-xl text-sm font-black text-zinc-200 bg-zinc-900 hover:border-lime-400 disabled:opacity-50 disabled:cursor-not-allowed uppercase tracking-wider"
            >
              {querying ? (
                <>
                  <Loader2 className="h-5 w-5 mr-2 animate-spin" />
                  Querying...
                </>
              ) : (
                'Query Payment Status'
              )}
            </button>
          </div>

          <div className="bg-white text-zinc-950 rounded-2xl p-6 border-4 border-zinc-950">
            <h2 className="font-black uppercase tracking-wider mb-4">Payment Record</h2>
            {payment ? (
              <div className="space-y-3 text-sm">
                <p><span className="font-black">out_trade_no:</span> {payment.out_trade_no}</p>
                <p><span className="font-black">scene:</span> {payment.scene}</p>
                <p><span className="font-black">auth_code_last4:</span> {payment.auth_code_last4}</p>
                <p><span className="font-black">trade_status:</span> {payment.trade_status}</p>
                <p><span className="font-black">trade_no:</span> {payment.trade_no || '-'}</p>
                <p><span className="font-black">buyer_user_id:</span> {payment.buyer_user_id || '-'}</p>
                <p><span className="font-black">buyer_logon_id:</span> {payment.buyer_logon_id || '-'}</p>
                <p><span className="font-black">retry_count:</span> {payment.retry_count}</p>
                <p><span className="font-black">last_query_status:</span> {payment.last_query_status || '-'}</p>
                <p><span className="font-black">paid_at:</span> {payment.paid_at || '-'}</p>
              </div>
            ) : (
              <p className="text-zinc-500 font-bold">No barcode payment attempt yet.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
