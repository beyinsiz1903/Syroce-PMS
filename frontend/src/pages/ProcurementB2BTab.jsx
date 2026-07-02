import { useTranslation } from "react-i18next";
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Loader2, TrendingDown, Store, Send, CheckCircle } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
const ProcurementB2BTab = () => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [proposals, setProposals] = useState([]);
  const [approving, setApproving] = useState(false);
  const [shippingAddress, setShippingAddress] = useState('Otel Merkez Depo, Kat -1');
  const [contactName, setContactName] = useState('Satın Alma Sorumlusu');
  const [contactPhone, setContactPhone] = useState('05551234567');
  useEffect(() => {
    fetchProposals();
  }, []);
  const fetchProposals = async () => {
    try {
      setLoading(true);
      const res = await axios.get('/procurement/b2b/proposals');
      setProposals(res.data.proposals || []);
    } catch (err) {
      console.error(err);
      toast.error('B2B teklifleri yüklenemedi. İzinlerinizi kontrol edin.');
    } finally {
      setLoading(false);
    }
  };
  const handleApprove = async () => {
    // Collect all lines across all vendors
    const lines = [];
    proposals.forEach(vendor => {
      const vendorLines = Array.isArray(vendor.lines) ? vendor.lines : [];
      vendorLines.forEach(item => {
        const qty = Number(item.proposed_qty || 0);
        if (qty > 0) {
          lines.push({
            inventory_item_id: item.inventory_item_id,
            mp_product_id: item.mp_product_id,
            quantity: qty
          });
        }
      });
    });
    if (lines.length === 0) {
      toast.error('Onaylanacak teklif bulunmuyor.');
      return;
    }
    try {
      setApproving(true);
      const payload = {
        lines,
        shipping_address: shippingAddress,
        contact_name: contactName,
        contact_phone: contactPhone,
        payment_method: 'bank_transfer',
        notes: 'Sistem tarafından otomatik B2B siparişi'
      };
      await axios.post('/procurement/b2b/orders/approve', payload);
      toast.success('B2B Siparişleri başarıyla tedarikçilere iletildi.');
      fetchProposals(); // refresh
    } catch (err) {
      console.error(err);
      toast.error('B2B sipariş onayı başarısız oldu.');
    } finally {
      setApproving(false);
    }
  };
  if (loading) {
    return <div className="flex justify-center p-12"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div>;
  }
  return <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-lg flex items-center gap-2">
              <TrendingDown className="w-5 h-5 text-indigo-600" />{t("cm.pages_ProcurementB2BTab.kritik_stok_otomatik_teklifler")}</CardTitle>
            <CardDescription>{t("cm.pages_ProcurementB2BTab.otel_sto\u011Funda_kritik_seviyeye")}</CardDescription>
          </div>
          <Button variant="outline" onClick={fetchProposals}>{t("cm.pages_ProcurementB2BTab.yenile")}</Button>
        </CardHeader>
        <CardContent>
          {proposals.length === 0 ? <div className="text-center py-8 border border-dashed rounded-lg bg-gray-50">
              <CheckCircle className="w-10 h-10 text-green-400 mx-auto mb-2" />
              <p className="text-gray-600 font-medium">{t("cm.pages_ProcurementB2BTab.t\xFCm_stok_seviyeleri_normal")}</p>
              <p className="text-sm text-gray-500">{t("cm.pages_ProcurementB2BTab.\u015Fu_anda_b2b_tedarik_\xF6nerisi_bu")}</p>
            </div> : <div className="space-y-6">
              {proposals.map(vendor => <div key={vendor.vendor_id} className="border rounded-lg p-4 bg-white shadow-sm">
                  <h4 className="font-bold flex items-center gap-2 text-slate-800 mb-3 border-b pb-2">
                    <Store className="w-4 h-4 text-slate-500" />{t("cm.pages_ProcurementB2BTab.tedarik\xE7i")}{vendor.vendor_name} ({vendor.vendor_id})
                  </h4>
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-gray-500 border-b">
                        <th className="pb-2">{t("cm.pages_ProcurementB2BTab.sku")}</th>
                        <th className="pb-2">{t("cm.pages_ProcurementB2BTab.otel_stok_ad\u0131")}</th>
                        <th className="pb-2">{t("cm.pages_ProcurementB2BTab.eksik_miktar")}</th>
                        <th className="pb-2">{t("cm.pages_ProcurementB2BTab.\xF6nerilen_sat\u0131n_alma")}</th>
                        <th className="pb-2 text-right">{t("cm.pages_ProcurementB2BTab.birim_fiyat")}</th>
                        <th className="pb-2 text-right">{t("cm.pages_ProcurementB2BTab.toplam")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(() => {
                  const vendorLines = Array.isArray(vendor.lines) ? vendor.lines : [];
                  return vendorLines.map((item, idx) => <tr key={idx} className="border-b last:border-0">
                            <td className="py-2 font-mono text-xs">{item.sku}</td>
                            <td className="py-2 font-medium">{item.name}</td>
                            <td className="py-2 text-red-600">{Number(item.reorder_level || 0) - Number(item.current_stock || 0) > 0 ? (Number(item.reorder_level || 0) - Number(item.current_stock || 0)).toFixed(0) : 0} {item.unit}</td>
                            <td className="py-2 text-indigo-600 font-semibold">{Number(item.proposed_qty || 0)} {item.unit}</td>
                            <td className="py-2 text-right">{item.unit_price} ₺</td>
                            <td className="py-2 text-right font-medium">{Number(item.total_price || 0).toFixed(2)} ₺</td>
                          </tr>);
                })()}
                    </tbody>
                  </table>
                  <div className="mt-3 text-right text-sm font-bold text-gray-800 bg-gray-50 p-2 rounded">{t("cm.pages_ProcurementB2BTab.tedarik\xE7i_ara_toplam")}{(() => {
                const vendorLines = Array.isArray(vendor.lines) ? vendor.lines : [];
                return vendorLines.reduce((sum, item) => sum + Number(item.total_price || 0), 0).toFixed(2);
              })()} ₺
                  </div>
                </div>)}

              <div className="bg-indigo-50 border border-indigo-100 p-4 rounded-lg mt-6">
                <h4 className="font-semibold text-indigo-900 mb-3">{t("cm.pages_ProcurementB2BTab.toplu_sipari\u015F_onay\u0131_t\xFCm_tedari")}</h4>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                  <div>
                    <Label className="text-indigo-800">{t("cm.pages_ProcurementB2BTab.teslimat_adresi")}</Label>
                    <Input value={shippingAddress} onChange={e => setShippingAddress(e.target.value)} className="bg-white" />
                  </div>
                  <div>
                    <Label className="text-indigo-800">{t("cm.pages_ProcurementB2BTab.i_leti\u015Fim_ki\u015Fisi")}</Label>
                    <Input value={contactName} onChange={e => setContactName(e.target.value)} className="bg-white" />
                  </div>
                  <div>
                    <Label className="text-indigo-800">{t("cm.pages_ProcurementB2BTab.i_leti\u015Fim_telefonu")}</Label>
                    <Input value={contactPhone} onChange={e => setContactPhone(e.target.value)} className="bg-white" />
                  </div>
                </div>
                <div className="flex justify-end">
                  <Button onClick={handleApprove} disabled={approving} className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2">
                    {approving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}{t("cm.pages_ProcurementB2BTab.t\xFCm_b2b_sipari\u015Flerini_onayla_v")}</Button>
                </div>
              </div>
            </div>}
        </CardContent>
      </Card>
    </div>;
};
export default ProcurementB2BTab;