import axios from 'axios';
import { FileText } from 'lucide-react';
import StatementsWorkspace from '@/components/statements/StatementsWorkspace';
import PerformanceReport from '@/components/statements/PerformanceReport';

export { monthEnd, monthStart, StatementLines, ADJUSTABLE } from '@/components/statements/StatementsWorkspace';

export default function AgencyStatements() {
  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4 sm:p-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold"><FileText size={22} /> Acente Performans ve Ekstreler</h1>
        <p className="text-sm text-slate-500">Acente Extranet dönem mutabakatı: ekstreyi siz, acente veya her ayın 1'inde sistem düzenler; iki taraf onaylar. Borçlu taraf ödemeyi bildirir, alacaklı doğrular.</p>
      </div>
      <PerformanceReport side="hotel" api={axios} path="/marketplace/hotel/reports/agency-performance" />
      <h2 className="pt-2 text-lg font-semibold">Dönem ekstreleri</h2>
      <StatementsWorkspace side="hotel" api={axios} base="/marketplace/hotel/statements" partiesPath="/marketplace/hotel/statements/agencies" />
    </div>
  );
}
