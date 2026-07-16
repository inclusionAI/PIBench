import { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Printer, ArrowLeft, Package } from 'lucide-react';
import { format } from 'date-fns';
import { toWords } from 'number-to-words';
import { apiFetch } from '../utils/api.js';
import { Invoice, InvoiceItem, Settings } from '../types.js';

export default function InvoiceView() {
  const { id } = useParams();
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const printRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    apiFetch(`/api/invoices/${id}`)
      .then(res => res.json())
      .then(data => setInvoice(data));
      
    apiFetch('/api/settings')
      .then(res => res.json())
      .then(data => setSettings(data));
  }, [id]);

  const handlePrint = () => {
    window.print();
  };

  if (!invoice) return <div className="p-8 text-center">Loading...</div>;

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between print:hidden">
        <Link to="/invoices" className="inline-flex items-center text-sm font-bold text-zinc-400 hover:text-white transition-colors">
          <ArrowLeft className="mr-2 h-5 w-5" />
          Back to Invoices
        </Link>
        <button
          onClick={handlePrint}
          className="inline-flex items-center px-6 py-3 border-2 border-zinc-950 text-sm font-bold rounded-xl shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] text-zinc-950 bg-lime-400 hover:bg-lime-300 hover:translate-y-[-2px] hover:translate-x-[-2px] hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] transition-all"
        >
          <Printer className="-ml-1 mr-2 h-5 w-5" />
          Print Invoice
        </button>
      </div>

      <div id="printable-invoice" ref={printRef} className="bg-white text-zinc-950 shadow-2xl rounded-3xl p-10 print:shadow-none print:p-0 print:rounded-none">
        {/* Header */}
        <div className="border-b-4 border-zinc-950 pb-8 mb-8 flex justify-between items-start relative">
          {invoice.status === 'cancelled' && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-20 z-0">
              <div className="text-9xl font-black text-rose-500 transform -rotate-12 border-8 border-rose-500 p-8 rounded-3xl">
                VOID
              </div>
            </div>
          )}
          <div className="flex items-center gap-4 relative z-10">
            {settings?.logo_url ? (
              <img src={settings.logo_url} alt="Logo" className="w-20 h-20 object-contain rounded-2xl border-4 border-zinc-950 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]" referrerPolicy="no-referrer" />
            ) : (
              <div className="bg-lime-400 p-4 rounded-2xl border-4 border-zinc-950 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
                <Package className="w-10 h-10 text-zinc-950" />
              </div>
            )}
            <div>
              <h1 className="text-4xl font-black uppercase tracking-tight text-zinc-950">{settings?.store_name || 'Bill Express'}</h1>
              <p className="text-sm font-bold text-zinc-600 mt-1 uppercase tracking-wider">Dealers in Fertilizers, Pesticides, Seeds & Micronutrients</p>
              <p className="text-sm font-medium text-zinc-500">{settings?.address || '123 Market Road, District, West Bengal - 700001'}</p>
              <p className="text-sm font-medium text-zinc-500">Ph: {settings?.phone || '9876543210'}</p>
            </div>
          </div>
          <div className="text-right relative z-10">
            <h2 className="text-3xl font-black uppercase border-4 border-zinc-950 inline-block px-6 py-2 rounded-xl transform rotate-2 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] bg-zinc-100">Tax Invoice</h2>
            <div className="mt-4 text-sm font-bold bg-zinc-100 py-2 px-4 rounded-lg border-2 border-zinc-200 inline-block text-left">
              <p>GSTIN: {settings?.gstin || '19AAAAA0000A1Z5'}</p>
              <p>State Code: {settings?.state_code || '19 (West Bengal)'}</p>
            </div>
          </div>
        </div>

        {/* Details */}
        <div className="flex justify-between mb-10 text-sm">
          <div className="w-1/2 pr-6 border-r-4 border-zinc-100">
            <h3 className="font-black text-zinc-400 uppercase tracking-wider mb-3 border-b-2 border-zinc-100 pb-2">Billed To:</h3>
            {invoice.customer_name ? (
              <div className="space-y-1">
                <p className="font-black text-xl text-zinc-950">{invoice.customer_name}</p>
                {invoice.customer_address && <p className="font-medium text-zinc-600">{invoice.customer_address}</p>}
                {invoice.customer_mobile && <p className="font-bold text-zinc-800">Ph: {invoice.customer_mobile}</p>}
                {invoice.customer_gstin && <p className="font-black text-zinc-950 mt-2 bg-lime-400 inline-block px-2 py-1 rounded">GSTIN: {invoice.customer_gstin}</p>}
                <p className="font-medium text-zinc-500 mt-2">Place of Supply: {invoice.customer_state || 'West Bengal'}</p>
              </div>
            ) : (
              <p className="font-black text-xl text-zinc-400 italic">Cash Sale</p>
            )}
          </div>
          <div className="w-1/2 pl-6">
            <div className="grid grid-cols-2 gap-y-4 gap-x-2">
              <p className="font-black text-zinc-400 uppercase tracking-wider">Invoice No:</p>
              <p className="font-black text-xl text-zinc-950 text-right">{invoice.invoice_number}</p>
              
              <p className="font-black text-zinc-400 uppercase tracking-wider">Date:</p>
              <p className="font-bold text-zinc-800 text-right">{format(new Date(invoice.date), 'dd-MMM-yyyy')}</p>
              
              <p className="font-black text-zinc-400 uppercase tracking-wider">Time:</p>
              <p className="font-bold text-zinc-800 text-right">{format(new Date(invoice.date), 'hh:mm a')}</p>

              <p className="font-black text-zinc-400 uppercase tracking-wider">Payment:</p>
              <p className={`font-bold text-right ${invoice.payment_status === 'Paid' ? 'text-lime-600' : invoice.payment_status === 'Partial' ? 'text-amber-600' : 'text-rose-600'}`}>
                {invoice.payment_status} (₹{invoice.amount_paid?.toFixed(2) || '0.00'})
              </p>
            </div>
          </div>
        </div>

        {/* Items Table */}
        <table className="w-full text-sm border-collapse border-4 border-zinc-950 mb-8">
          <thead className="bg-zinc-950 text-white">
            <tr>
              <th className="border-2 border-zinc-950 px-3 py-3 text-center w-12 font-black uppercase tracking-wider">#</th>
              <th className="border-2 border-zinc-950 px-3 py-3 text-left font-black uppercase tracking-wider">Description of Goods</th>
              <th className="border-2 border-zinc-950 px-3 py-3 text-center w-20 font-black uppercase tracking-wider">HSN</th>
              <th className="border-2 border-zinc-950 px-3 py-3 text-right w-16 font-black uppercase tracking-wider">Qty</th>
              <th className="border-2 border-zinc-950 px-3 py-3 text-center w-16 font-black uppercase tracking-wider">Unit</th>
              <th className="border-2 border-zinc-950 px-3 py-3 text-right w-24 font-black uppercase tracking-wider">Rate (₹)</th>
              <th className="border-2 border-zinc-950 px-3 py-3 text-right w-24 font-black uppercase tracking-wider">Taxable</th>
              {invoice.igst_total > 0 ? (
                <th colSpan={2} className="border-2 border-zinc-950 px-3 py-3 text-center font-black uppercase tracking-wider">IGST</th>
              ) : (
                <>
                  <th className="border-2 border-zinc-950 px-3 py-3 text-right w-16 font-black uppercase tracking-wider">CGST</th>
                  <th className="border-2 border-zinc-950 px-3 py-3 text-right w-16 font-black uppercase tracking-wider">SGST</th>
                </>
              )}
              <th className="border-2 border-zinc-950 px-3 py-3 text-right w-28 font-black uppercase tracking-wider">Total (₹)</th>
            </tr>
          </thead>
          <tbody className="font-medium">
            {invoice.items.map((item: InvoiceItem, index: number) => (
              <tr key={item.id} className="even:bg-zinc-50">
                <td className="border-2 border-zinc-950 px-3 py-2 text-center font-bold">{index + 1}</td>
                <td className="border-2 border-zinc-950 px-3 py-2">
                  <span className="font-black text-base">{item.product_name}</span>
                  <span className="block text-xs font-bold text-zinc-500 mt-1">Code: {item.product_code}</span>
                </td>
                <td className="border-2 border-zinc-950 px-3 py-2 text-center font-mono">{item.hsn_code}</td>
                <td className="border-2 border-zinc-950 px-3 py-2 text-right font-bold">{item.quantity}</td>
                <td className="border-2 border-zinc-950 px-3 py-2 text-center">{item.unit}</td>
                <td className="border-2 border-zinc-950 px-3 py-2 text-right">{item.price_ex_gst.toFixed(2)}</td>
                <td className="border-2 border-zinc-950 px-3 py-2 text-right">{(item.quantity * item.price_ex_gst).toFixed(2)}</td>
                {invoice.igst_total > 0 ? (
                  <td colSpan={2} className="border-2 border-zinc-950 px-3 py-2 text-center text-xs">
                    <span className="font-bold">{(item.igst_amount || 0).toFixed(2)}</span><br/>
                    <span className="text-zinc-500 font-bold">({item.gst_rate}%)</span>
                  </td>
                ) : (
                  <>
                    <td className="border-2 border-zinc-950 px-3 py-2 text-right text-xs">
                      <span className="font-bold">{item.cgst_amount.toFixed(2)}</span><br/>
                      <span className="text-zinc-500 font-bold">({item.gst_rate / 2}%)</span>
                    </td>
                    <td className="border-2 border-zinc-950 px-3 py-2 text-right text-xs">
                      <span className="font-bold">{item.sgst_amount.toFixed(2)}</span><br/>
                      <span className="text-zinc-500 font-bold">({item.gst_rate / 2}%)</span>
                    </td>
                  </>
                )}
                <td className="border-2 border-zinc-950 px-3 py-2 text-right font-black text-base">{item.total.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot className="bg-zinc-100">
            <tr>
              <td colSpan={6} className="border-2 border-zinc-950 px-3 py-3 text-right font-black uppercase tracking-wider">Total</td>
              <td className="border-2 border-zinc-950 px-3 py-3 text-right font-black">{invoice.subtotal.toFixed(2)}</td>
              {invoice.igst_total > 0 ? (
                <td colSpan={2} className="border-2 border-zinc-950 px-3 py-3 text-center font-black">{(invoice.igst_total || 0).toFixed(2)}</td>
              ) : (
                <>
                  <td className="border-2 border-zinc-950 px-3 py-3 text-right font-black">{invoice.cgst_total.toFixed(2)}</td>
                  <td className="border-2 border-zinc-950 px-3 py-3 text-right font-black">{invoice.sgst_total.toFixed(2)}</td>
                </>
              )}
              <td className="border-2 border-zinc-950 px-3 py-3 text-right font-black text-xl bg-lime-400">{invoice.grand_total.toFixed(2)}</td>
            </tr>
          </tfoot>
        </table>

        {/* Footer */}
        <div className="flex justify-between items-end mt-10">
          <div className="w-2/3">
            <p className="text-sm font-black text-zinc-400 uppercase tracking-wider mb-2">Amount in words:</p>
            <p className="font-black text-xl text-zinc-950 capitalize bg-zinc-100 inline-block px-4 py-2 rounded-lg">
              Rupees {toWords(Math.round(invoice.grand_total))} Only
            </p>
            
            <div className="mt-8 text-xs font-medium text-zinc-600 bg-zinc-50 p-4 rounded-xl border-2 border-zinc-200">
              <p className="font-black text-zinc-950 uppercase tracking-wider mb-2">Terms & Conditions:</p>
              <ol className="list-decimal pl-4 space-y-1">
                <li>Goods once sold will not be taken back.</li>
                <li>Interest @ 18% p.a. will be charged if payment is delayed.</li>
                <li>Subject to local jurisdiction.</li>
              </ol>
            </div>
          </div>
          
          <div className="w-1/3 text-center">
            <p className="font-black text-zinc-950 mb-16 uppercase tracking-wider">For Bill Express</p>
            <div className="border-t-4 border-zinc-950 pt-2 mx-8">
              <p className="text-sm font-bold text-zinc-600 uppercase tracking-wider">Authorised Signatory</p>
            </div>
          </div>
        </div>
      </div>
      
      {/* Print Styles */}
      <style>{`
        @media print {
          body * {
            visibility: hidden;
          }
          #printable-invoice, #printable-invoice * {
            visibility: visible;
          }
          #printable-invoice {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            padding: 0;
            margin: 0;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
          }
          @page {
            size: auto;
            margin: 12mm;
          }
        }
      `}</style>
    </div>
  );
}
