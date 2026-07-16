import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, Loader2, QrCode, RefreshCw } from 'lucide-react';
import { apiFetch } from '../utils/api.js';

type PaymentRecord = {
  id: number;
  invoice_id: number;
  invoice_number: string;
  out_trade_no: string;
  trade_no?: string;
  subject: string;
  total_amount: number;
  status: string;
  qr_code: string;
  payment_status: string;
  amount_paid: number;
  grand_total: number;
  paid_at?: string;
};

export default function AlipayPayment() {
  const { outTradeNo } = useParams();
  const [payment, setPayment] = useState<PaymentRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [querying, setQuerying] = useState(false);
  const [error, setError] = useState('');

  const loadPayment = async () => {
    if (!outTradeNo) return;
    try {
      const res = await apiFetch(`/api/alipay/payments/${outTradeNo}`);
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || 'Payment not found');
        return;
      }
      setPayment(data.payment);
      setError('');
    } catch (err) {
      setError('Failed to load payment');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPayment();
    const timer = window.setInterval(loadPayment, 2500);
    return () => window.clearInterval(timer);
  }, [outTradeNo]);

  const queryPayment = async () => {
    if (!outTradeNo) return;
    setQuerying(true);
    try {
      const res = await apiFetch(`/api/alipay/payments/${outTradeNo}/query`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok || !data.success) {
        setError(data.error || 'Query payment failed');
      }
      await loadPayment();
    } catch (err) {
      setError('Query payment failed');
    } finally {
      setQuerying(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center text-zinc-400">
        <Loader2 className="h-8 w-8 animate-spin mr-3" />
        Loading payment...
      </div>
    );
  }

  if (error || !payment) {
    return (
      <div className="space-y-6 max-w-3xl mx-auto">
        <Link to="/invoices" className="inline-flex items-center text-sm font-bold text-zinc-400 hover:text-white">
          <ArrowLeft className="mr-2 h-5 w-5" />
          Back to Invoices
        </Link>
        <div className="bg-rose-500/10 border-2 border-rose-500 rounded-2xl p-6 text-rose-300 font-bold">
          {error || 'Payment not found'}
        </div>
      </div>
    );
  }

  const paid = payment.status === 'TRADE_SUCCESS' && payment.payment_status === 'Paid';

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <Link to="/invoices" className="inline-flex items-center text-sm font-bold text-zinc-400 hover:text-white">
          <ArrowLeft className="mr-2 h-5 w-5" />
          Back to Invoices
        </Link>
        <button
          onClick={loadPayment}
          className="inline-flex items-center px-4 py-2 rounded-xl border-2 border-zinc-800 text-zinc-300 hover:text-white hover:border-lime-400"
        >
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </button>
      </div>

      <div className="bg-zinc-900 border-2 border-zinc-800 rounded-3xl p-8">
        <div className="flex items-start justify-between gap-6 border-b-2 border-zinc-800 pb-6 mb-8">
          <div>
            <p className="text-sm font-black uppercase tracking-wider text-lime-400 mb-2">Alipay Order Code</p>
            <h1 className="text-3xl font-black text-white">{payment.invoice_number}</h1>
            <p className="text-zinc-400 font-medium mt-2">{payment.subject}</p>
          </div>
          <div className="text-right">
            <p className="text-sm font-black uppercase tracking-wider text-zinc-500">Amount</p>
            <p className="text-4xl font-black text-white">₹{Number(payment.total_amount).toFixed(2)}</p>
            <span className={`inline-flex mt-3 px-3 py-1 rounded-full text-xs font-black uppercase ${paid ? 'bg-lime-400 text-zinc-950' : 'bg-amber-400 text-zinc-950'}`}>
              {paid ? 'Paid' : payment.status}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <div className="bg-white text-zinc-950 rounded-2xl p-8 border-4 border-zinc-950">
            <div className="flex items-center mb-4">
              <QrCode className="h-6 w-6 mr-2" />
              <h2 className="font-black uppercase tracking-wider">QRCode Payment</h2>
            </div>
            <div className="aspect-square border-8 border-zinc-950 rounded-xl p-6 grid grid-cols-7 gap-1 bg-white">
              {Array.from({ length: 49 }).map((_, index) => (
                <div
                  key={index}
                  className={(index * 17 + payment.out_trade_no.length) % 5 < 2 ? 'bg-zinc-950' : 'bg-white'}
                />
              ))}
            </div>
            <p className="mt-4 text-xs font-mono break-all bg-zinc-100 border-2 border-zinc-200 rounded-lg p-3">
              {payment.qr_code}
            </p>
          </div>

          <div className="bg-zinc-950 rounded-2xl p-8 border-2 border-zinc-800">
            <div className="flex items-center mb-4">
              <RefreshCw className="h-6 w-6 mr-2 text-lime-400" />
              <h2 className="font-black uppercase tracking-wider text-white">Gateway Status</h2>
            </div>

            <div className="space-y-2 text-sm text-zinc-400">
              <p><span className="font-bold text-zinc-200">out_trade_no:</span> {payment.out_trade_no}</p>
              <p><span className="font-bold text-zinc-200">trade_no:</span> {payment.trade_no || '-'}</p>
              <p><span className="font-bold text-zinc-200">invoice_id:</span> {payment.invoice_id}</p>
              <p><span className="font-bold text-zinc-200">invoice paid:</span> ₹{Number(payment.amount_paid || 0).toFixed(2)} / ₹{Number(payment.grand_total).toFixed(2)}</p>
            </div>

            <button
              onClick={queryPayment}
              disabled={querying || paid}
              className="mt-8 w-full flex justify-center items-center py-4 px-4 border-2 border-zinc-950 rounded-xl shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] text-lg font-black text-zinc-950 bg-lime-400 hover:bg-lime-300 disabled:opacity-50 disabled:cursor-not-allowed uppercase tracking-wider"
            >
              {paid ? (
                <>
                  <CheckCircle2 className="h-6 w-6 mr-2" />
                  Payment Complete
                </>
              ) : querying ? (
                <>
                  <Loader2 className="h-6 w-6 mr-2 animate-spin" />
                  Querying...
                </>
              ) : (
                'Query Payment Status'
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
