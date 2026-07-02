import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ChefHat } from 'lucide-react';
import { Info, Modal } from '../_shared';
const KitchenModal = ({
  kitchenData,
  onClose
}) => <Modal title={`Mutfak Fişi — ${kitchenData.event_name}`} onClose={onClose} wide>
    <div className="space-y-3 text-sm">
      <Card><CardContent className="p-3 grid grid-cols-3 gap-2 text-xs">
        <Info l="Beklenen Pax" v={kitchenData.expected_pax} />
        <Info l="İlk Servis" v={kitchenData.first_service_at?.slice(0, 16) || '—'} />
        <Info l="Toplam Hat" v={kitchenData.tickets.length} />
      </CardContent></Card>

      {kitchenData.all_allergens?.length > 0 && <div className="bg-red-50 border border-red-200 rounded p-2 text-xs">
          <strong className="text-red-700">Alerjenler:</strong> {kitchenData.all_allergens.join(', ')}
        </div>}
      {kitchenData.all_dietary_tags?.length > 0 && <div className="bg-emerald-50 border border-emerald-200 rounded p-2 text-xs">
          <strong className="text-emerald-700">Diyet Etiketleri:</strong> {kitchenData.all_dietary_tags.join(', ')}
        </div>}

      {kitchenData.tickets.length === 0 ? <p className="text-center text-gray-500 p-4">F&B menü hattı yok.</p> : kitchenData.tickets.map((t, i) => <Card key={t.id || i}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <ChefHat className="w-4 h-4 text-amber-600" />
                {t.menu_name} × {t.qty_pax} pax
              </CardTitle>
              <CardDescription>
                Hazırlık tamamlanmalı: <span className="font-mono font-bold text-red-600">
                  {t.prep_by?.slice(0, 16) || '—'}
                </span> ({t.prep_lead_minutes}dk lead)
              </CardDescription>
            </CardHeader>
            <CardContent>
              {t.courses?.length > 0 && <table className="w-full text-xs border-collapse">
                  <thead className="bg-slate-50"><tr>
                    <th className="border p-1">Kurs</th>
                    <th className="border p-1 text-left">Yemek</th>
                    <th className="border p-1 text-left">Açıklama</th>
                  </tr></thead>
                  <tbody>
                    {t.courses.map((c, j) => <tr key={j}>
                        <td className="border p-1 text-center">{c.course_type}</td>
                        <td className="border p-1 font-semibold">{c.name}</td>
                        <td className="border p-1 text-gray-600">{c.description || '—'}</td>
                      </tr>)}
                  </tbody>
                </table>}
              {t.allergens?.length > 0 && <div className="text-xs text-red-600 mt-2">
                  Alerjenler: {t.allergens.join(', ')}
                </div>}
              {t.dietary_tags?.length > 0 && <div className="text-xs text-emerald-600 mt-1">
                  Diyet: {t.dietary_tags.join(', ')}
                </div>}
            </CardContent>
          </Card>)}

      <div className="text-right">
        <Button variant="outline" onClick={() => window.print()}>Yazdır</Button>
        <Button variant="ghost" onClick={onClose}>Kapat</Button>
      </div>
    </div>
  </Modal>;
export default KitchenModal;