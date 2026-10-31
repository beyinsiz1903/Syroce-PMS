import React, { useEffect, useState } from 'react';
import { fetchJsonWithRetry } from '@/lib/fetchRetry';

const DEMO_TENANT = '5bad4a34-6ee3-4566-9053-741b7375a9cf';

export default function DemoSourceNotice({ tenant }) {
  const [status, setStatus] = useState(null);
  const isDemo = tenant?.id === DEMO_TENANT;
  useEffect(() => {
    let active = true;
    setStatus(null);
    if (isDemo) {
      fetchJsonWithRetry('/api/pms/demo-source-remediation/status', { credentials: 'include' })
        .then(value => { if (active) setStatus(value); })
        .catch(() => { /* The conservative demo notice remains visible. */ });
    }
    return () => { active = false; };
  }, [isDemo]);
  if (!isDemo) return null;
  return <aside role="note" data-testid="demo-source-notice" className="mb-4 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 print:block">
    <p className="font-semibold">Kaynak doğrulama notu — gerçek mali doğrulama değildir</p>
    <p>Örnek işlemler ve yeniden kurulan kur, vade, mahsup ve vergi bilgileri tarihî kaynak belgesi yerine geçmez.</p>
    {status?.applied && <details className="mt-2">
      <summary className="cursor-pointer">Kaynak geçmişini koruyan düzeltme özeti</summary>
      <p>{status.result?.document_count} kaynak için önceki sürüm korundu; {status.result?.cashier_appended} kasa kaynak kaydı tamamlandı.</p>
      <p>69 tarihî denetim bulgusu ayrı kanıt kaydında belgelendi. Güncel zincir durumunu Denetim Merkezi'nden doğrulayın; özgün mühürler yeniden üretilmez.</p>
      <p className="break-all text-xs">{status.policy_id}</p>
    </details>}
  </aside>;
}
