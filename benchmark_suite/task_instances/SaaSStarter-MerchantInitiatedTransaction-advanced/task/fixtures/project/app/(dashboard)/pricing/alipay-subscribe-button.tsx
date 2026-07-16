'use client';

import { useEffect, useState } from 'react';
import { CreditCard, Loader2, RefreshCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';

type Status = {
  planName: string | null;
  subscriptionStatus: string | null;
  alipayExternalAgreementNo: string | null;
  alipayAgreementNo: string | null;
  alipayLastOutTradeNo: string | null;
  alipayLastAmount: string | null;
  alipayPaymentStatus: string | null;
};

type SignResult = {
  mode?: string;
  externalAgreementNo?: string;
  outTradeNo?: string;
  orderString?: string;
  mockAutoNotify?: { ok?: boolean; status?: number } | null;
  error?: string;
};

async function readJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(data.error || text || `HTTP ${response.status}`);
  }
  return data;
}

export function AlipaySubscribeButton({ planName, amount }: { planName: string; amount: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [result, setResult] = useState<SignResult | null>(null);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  async function refreshStatus() {
    const data = await readJson<Status>(await fetch('/api/alipay/status?teamId=1', { cache: 'no-store' }));
    setStatus(data);
    return data;
  }

  async function subscribe() {
    setLoading(true);
    setMessage('');
    try {
      const data = await readJson<SignResult>(await fetch('/api/alipay/sign-contract', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ teamId: 1, amount, planName }),
      }));
      setResult(data);
      const nextStatus = await refreshStatus();
      if (data.mockAutoNotify?.ok && nextStatus.subscriptionStatus === 'active') {
        setMessage('Mock Alipay agreement completed. Subscription is active.');
      } else {
        setMessage('Alipay agreement request created. Complete the agreement in Alipay to activate this subscription.');
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to start Alipay subscription.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshStatus().catch(() => undefined);
  }, []);

  return (
    <div className="rounded-md border border-gray-200 bg-white p-3">
      <div className="flex gap-2">
        <Button type="button" className="flex-1 rounded-full" onClick={subscribe} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CreditCard className="h-4 w-4" />}
          Subscribe with Alipay
        </Button>
        <Button type="button" variant="outline" size="icon" onClick={() => refreshStatus()} aria-label="Refresh subscription status">
          <RefreshCcw className="h-4 w-4" />
        </Button>
      </div>
      <div className="mt-3 space-y-1 text-xs text-gray-600">
        <p>Subscription: <span className="font-medium text-gray-900">{status?.subscriptionStatus || '-'}</span></p>
        <p>Payment: <span className="font-medium text-gray-900">{status?.alipayPaymentStatus || '-'}</span></p>
        {status?.alipayAgreementNo ? <p className="break-all">Agreement: {status.alipayAgreementNo}</p> : null}
        {result?.externalAgreementNo ? <p className="break-all">Request: {result.externalAgreementNo}</p> : null}
        {message ? <p className="text-gray-700">{message}</p> : null}
      </div>
    </div>
  );
}
