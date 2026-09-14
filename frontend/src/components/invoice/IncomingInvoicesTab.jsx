import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { useCurrency } from '@/context/CurrencyContext';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { RefreshCw, Check, X, FileText, Download } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";

const IncomingInvoicesTab = () => {
  const { t } = useTranslation();
  const { amount: fmtMoney } = useCurrency();
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [answerDialog, setAnswerDialog] = useState({ open: false, invoice: null, type: null, note: '' });

  const fetchInvoices = useCallback(async () => {
    try {
      setLoading(true);
      const res = await axios.get('/api/integrations/incoming-invoices?limit=100');
      setInvoices(res.data?.items || []);
    } catch (err) {
      console.error(err);
      toast.error(t('invoice.incoming.fetchError') || 'Gelen faturalar yüklenirken hata oluştu.');
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchInvoices();
  }, [fetchInvoices]);

  const handleSync = async () => {
    try {
      setSyncing(true);
      const res = await axios.post('/api/integrations/incoming-invoices/sync', {});
      toast.success(t('invoice.incoming.syncSuccess') || `Senkronizasyon tamamlandı. ${res.data?.invoices_created || 0} yeni fatura eklendi.`);
      fetchInvoices();
    } catch (err) {
      console.error(err);
      toast.error(t('invoice.incoming.syncError') || 'Senkronizasyon başarısız oldu.');
    } finally {
      setSyncing(false);
    }
  };

  const handleAnswerSubmit = async () => {
    try {
      const { invoice, type, note } = answerDialog;
      await axios.post(`/api/integrations/incoming-invoices/${invoice.id}/answer`, {
        answer: type,
        note: note || undefined,
        request_uuid: crypto.randomUUID(),
      });
      toast.success(t('invoice.incoming.answerSuccess') || 'Fatura yanıtı başarıyla iletildi.');
      setAnswerDialog({ open: false, invoice: null, type: null, note: '' });
      fetchInvoices();
    } catch (err) {
      console.error(err);
      toast.error(t('invoice.incoming.answerError') || 'Fatura yanıtı iletilemedi.');
    }
  };

  const getStatusBadge = (invoice) => {
    const statusMap = {
      'PENDING': { label: 'Bekliyor', color: 'bg-yellow-100 text-yellow-800' },
      'APPROVE': { label: 'Kabul Edildi', color: 'bg-green-100 text-green-800' },
      'REJECT': { label: 'Reddedildi', color: 'bg-red-100 text-red-800' },
    };
    const answer = invoice.answer_status;
    const mapped = statusMap[answer] || { label: answer, color: 'bg-gray-100 text-gray-800' };
    return <Badge variant="outline" className={`font-medium ${mapped.color}`}>{mapped.label}</Badge>;
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-xl font-bold">{t('invoice.incoming.title') || 'Gelen e-Faturalar'}</h2>
          <p className="text-sm text-gray-500">{t('invoice.incoming.description') || 'Entegratörünüze (Nilvera) gelen faturalarınızı buradan yönetebilirsiniz.'}</p>
        </div>
        <Button onClick={handleSync} disabled={syncing}>
          <RefreshCw className={`w-4 h-4 mr-2 ${syncing ? 'animate-spin' : ''}`} />
          {t('invoice.incoming.sync') || 'Eşitle (Sync)'}
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8 text-center text-gray-500">Yükleniyor...</div>
          ) : invoices.length === 0 ? (
            <div className="p-8 text-center text-gray-500">Gelen faturanız bulunmuyor.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="px-4 py-3 font-medium text-gray-500">Tarih</th>
                    <th className="px-4 py-3 font-medium text-gray-500">Fatura No</th>
                    <th className="px-4 py-3 font-medium text-gray-500">Gönderici</th>
                    <th className="px-4 py-3 font-medium text-gray-500 text-right">Tutar</th>
                    <th className="px-4 py-3 font-medium text-gray-500 text-center">Durum</th>
                    <th className="px-4 py-3 font-medium text-gray-500 text-right">İşlem</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {invoices.map(inv => (
                    <tr key={inv.id} className="hover:bg-gray-50/50">
                      <td className="px-4 py-3 whitespace-nowrap">
                        {new Date(inv.issue_date).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap font-medium text-blue-600">
                        {inv.document_number}
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-medium">{inv.sender_name}</div>
                        <div className="text-xs text-gray-500">VKN/TCKN: {inv.sender_tax_number}</div>
                      </td>
                      <td className="px-4 py-3 text-right font-medium">
                        {fmtMoney(inv.payable_amount, inv.currency || 'TRY')}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {getStatusBadge(inv)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {inv.answer_status === 'PENDING' && inv.profile === 'TICARIFATURA' && (
                          <div className="flex items-center justify-end gap-2">
                            <Button size="sm" variant="outline" className="text-green-600 border-green-200 hover:bg-green-50"
                              onClick={() => setAnswerDialog({ open: true, invoice: inv, type: 'APPROVE', note: '' })}>
                              <Check className="w-4 h-4" />
                            </Button>
                            <Button size="sm" variant="outline" className="text-red-600 border-red-200 hover:bg-red-50"
                              onClick={() => setAnswerDialog({ open: true, invoice: inv, type: 'REJECT', note: '' })}>
                              <X className="w-4 h-4" />
                            </Button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={answerDialog.open} onOpenChange={(open) => !open && setAnswerDialog(prev => ({ ...prev, open: false }))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {answerDialog.type === 'APPROVE' ? 'Faturayı Kabul Et' : 'Faturayı Reddet'}
            </DialogTitle>
            <DialogDescription>
              <strong>{answerDialog.invoice?.document_number}</strong> numaralı, 
              <strong> {answerDialog.invoice?.sender_name}</strong> tarafından gönderilen faturayı 
              {answerDialog.type === 'APPROVE' ? ' KABUL' : ' RED'} etmek üzeresiniz.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Açıklama / Not (Opsiyonel)
            </label>
            <Textarea
              placeholder={answerDialog.type === 'REJECT' ? 'Reddetme sebebinizi yazabilirsiniz...' : 'Not ekleyebilirsiniz...'}
              value={answerDialog.note}
              onChange={(e) => setAnswerDialog(prev => ({ ...prev, note: e.target.value }))}
              rows={3}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAnswerDialog(prev => ({ ...prev, open: false }))}>
              İptal
            </Button>
            <Button 
              variant={answerDialog.type === 'APPROVE' ? 'default' : 'destructive'} 
              onClick={handleAnswerSubmit}
            >
              Onayla ve {answerDialog.type === 'APPROVE' ? 'Kabul Et' : 'Reddet'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default IncomingInvoicesTab;
