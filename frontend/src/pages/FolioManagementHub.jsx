import { useNavigate } from 'react-router-dom';
import { ArrowRight, Building2, FileText, ReceiptText, Route, WalletCards } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

const WORKSPACES = [
  {
    key: 'guest-folios',
    title: 'Misafir folyosu ve tahsilat',
    description: 'Rezervasyon hesabını, ücretleri, ödemeleri ve açık bakiyeleri yönetin.',
    path: '/app/pms?tab=cashier',
    action: 'Folyoları aç',
    icon: WalletCards,
  },
  {
    key: 'routing',
    title: 'Ücret yönlendirme kuralları',
    description: 'Oda, vergi veya hizmet ücretlerini şirket, grup ya da başka bir folyoya yönlendirin.',
    path: '/folio-routing',
    action: 'Kuralları yönet',
    icon: Route,
  },
  {
    key: 'group-folio',
    title: 'Grup ve ana hesap folyoları',
    description: 'Grup rezervasyonlarını birleştirin; toplu tahsilat ve ödeme dağıtımı yapın.',
    path: '/group-folio',
    action: 'Grup folyolarını aç',
    icon: Building2,
  },
  {
    key: 'invoices',
    title: 'Fatura ve belgeler',
    description: 'Folyo bakiyesinden fatura oluşturun, ödeme ve belge durumlarını izleyin.',
    path: '/app/invoices',
    action: 'Faturaları aç',
    icon: FileText,
  },
];

export default function FolioManagementHub() {
  const navigate = useNavigate();

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-4 md:p-6" data-testid="folio-management-hub">
      <header className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm md:p-6">
        <div className="flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-slate-900 text-white">
            <ReceiptText className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-950">Folyo ve Hesap Yönetimi</h1>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">
              Misafir hesabından grup folyosuna, ücret yönlendirmeden tahsilat ve faturaya kadar tüm hesap işlemleri tek merkezde.
            </p>
          </div>
        </div>
      </header>

      <section className="grid gap-4 md:grid-cols-2">
        {WORKSPACES.map(({ key, title, description, path, action, icon: Icon }) => (
          <Card key={key} className="flex min-h-56 flex-col border-slate-200 shadow-sm">
            <CardHeader>
              <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-lg bg-slate-100 text-slate-700">
                <Icon className="h-5 w-5" />
              </div>
              <CardTitle className="text-base">{title}</CardTitle>
              <CardDescription className="leading-5">{description}</CardDescription>
            </CardHeader>
            <CardContent className="mt-auto">
              <Button className="w-full" onClick={() => navigate(path)} data-testid={`open-${key}`}>
                {action}<ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </CardContent>
          </Card>
        ))}
      </section>
    </main>
  );
}
