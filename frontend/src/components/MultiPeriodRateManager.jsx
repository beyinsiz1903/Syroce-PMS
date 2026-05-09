import React, { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Calendar, Plus, Trash2, Save, DollarSign } from 'lucide-react';
import { useTranslation } from 'react-i18next';

/**
 * Multi-Period Rate Manager
 * Manages multiple rate periods for operators (TUI, HolidayCheck, etc)
 * Example: 01.05-31.05, 01.06-15.06, 16.06-30.06
 */
const MultiPeriodRateManager = ({ operatorId, operatorName, roomTypeId }) => {
  const { t } = useTranslation();
  const [ratePeriods, setRatePeriods] = useState([
    // Example structure
    // { id: '1', start_date: '2025-05-01', end_date: '2025-05-31', rate: 150, currency: 'USD' }
  ]);
  const [loading, setLoading] = useState(false);

  React.useEffect(() => {
    if (operatorId && roomTypeId) {
      loadRatePeriods();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [operatorId, roomTypeId]);

  const loadRatePeriods = async () => {
    try {
      const response = await axios.get(`/rates/periods?operator_id=${operatorId}&room_type_id=${roomTypeId}`);
      setRatePeriods(response.data.periods || []);
    } catch (error) {
      console.error('Failed to load rate periods:', error);
    }
  };

  const addPeriod = () => {
    const newPeriod = {
      id: `temp_${Date.now()}`,
      start_date: '',
      end_date: '',
      rate: 0,
      currency: 'USD',
      isNew: true
    };
    setRatePeriods([...ratePeriods, newPeriod]);
  };

  const updatePeriod = (id, field, value) => {
    setRatePeriods(ratePeriods.map(period => 
      period.id === id ? { ...period, [field]: value } : period
    ));
  };

  const deletePeriod = (id) => {
    setRatePeriods(ratePeriods.filter(period => period.id !== id));
  };

  const saveAllPeriods = async () => {
    setLoading(true);
    try {
      await axios.post('/rates/periods/bulk-update', {
        operator_id: operatorId,
        room_type_id: roomTypeId,
        periods: ratePeriods
      });
      toast.success(`${ratePeriods.length} rate periods saved for ${operatorName}`);
      loadRatePeriods();
    } catch (error) {
      toast.error('Fiyat dönemleri kaydedilemedi');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Calendar className="w-5 h-5 text-blue-600" />
            <span>{t('cm.components_MultiPeriodRateManager.donem_bazli_tarifeler')}</span>
          </div>
          <Button onClick={addPeriod} size="sm" variant="outline">
            <Plus className="w-4 h-4 mr-2" />
            {t('cm.components_MultiPeriodRateManager.donem_ekle')}
          </Button>
        </CardTitle>
        <CardDescription>
          {operatorName} {t('cm.components_MultiPeriodRateManager.donem_donem_farkli_fiyatlandirma')}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {ratePeriods.length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              {t('cm.components_MultiPeriodRateManager.henuz_donem_tanimlanmamis_donem_ekle_ile')}
            </div>
          ) : (
            ratePeriods.map((period, index) => (
              <div key={period.id} className="p-4 bg-gray-50 rounded-lg border space-y-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-semibold text-gray-700">
                    {t('cm.components_MultiPeriodRateManager.donem')} {index + 1}
                  </span>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => deletePeriod(period.id)}
                    className="text-red-600 hover:bg-red-50"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  {/* Start Date */}
                  <div>
                    <Label className="text-xs">{t('cm.components_MultiPeriodRateManager.baslangic_tarihi')}</Label>
                    <Input
                      type="date"
                      value={period.start_date}
                      onChange={(e) => updatePeriod(period.id, 'start_date', e.target.value)}
                      className="mt-1"
                    />
                  </div>

                  {/* End Date */}
                  <div>
                    <Label className="text-xs">{t('cm.components_MultiPeriodRateManager.bitis_tarihi')}</Label>
                    <Input
                      type="date"
                      value={period.end_date}
                      onChange={(e) => updatePeriod(period.id, 'end_date', e.target.value)}
                      className="mt-1"
                    />
                  </div>
                </div>

                {/* Rate */}
                <div>
                  <Label className="text-xs">{t('cm.components_MultiPeriodRateManager.fiyat_gunluk')}</Label>
                  <div className="flex gap-2 mt-1">
                    <div className="relative flex-1">
                      <DollarSign className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
                      <Input
                        type="number"
                        value={period.rate}
                        onChange={(e) => updatePeriod(period.id, 'rate', parseFloat(e.target.value))}
                        className="pl-9"
                        placeholder="0.00"
                      />
                    </div>
                    <select
                      value={period.currency}
                      onChange={(e) => updatePeriod(period.id, 'currency', e.target.value)}
                      className="border rounded px-3 py-2 text-sm"
                    >
                      <option value="USD">USD</option>
                      <option value="EUR">EUR</option>
                      <option value="TRY">TRY</option>
                      <option value="GBP">GBP</option>
                    </select>
                  </div>
                </div>

                {/* Period Display */}
                <div className="text-xs text-gray-600 bg-white p-2 rounded border">
                  {period.start_date ? new Date(period.start_date).toLocaleDateString('tr-TR') : '??.??.????'} 
                  {' '}-{' '}
                  {period.end_date ? new Date(period.end_date).toLocaleDateString('tr-TR') : '??.??.????'}
                  {period.rate > 0 && (
                    <span className="ml-2 font-semibold text-green-700">
                      | {period.rate} {period.currency} / gece
                    </span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Save Button */}
        {ratePeriods.length > 0 && (
          <Button
            onClick={saveAllPeriods}
            disabled={loading}
            className="w-full mt-4 bg-blue-600 hover:bg-blue-700"
          >
            <Save className="w-4 h-4 mr-2" />
            {loading ? 'Kaydediliyor...' : `${ratePeriods.length} Dönemi Kaydet`}
          </Button>
        )}

        {/* Examples */}
        <div className="mt-4 p-3 bg-blue-50 border-l-4 border-blue-500 rounded text-xs">
          <strong>{t('cm.components_MultiPeriodRateManager.ornek_donemler')}</strong>
          <ul className="list-disc list-inside mt-1 space-y-0.5 text-gray-700">
            <li>{t('cm.components_MultiPeriodRateManager.01_05_31_05_dusuk_sezon_120_gece')}</li>
            <li>01.06 - 15.06 → Orta Sezon (€150/gece)</li>
            <li>{t('cm.components_MultiPeriodRateManager.16_06_30_06_yuksek_sezon_200_gece')}</li>
          </ul>
        </div>
      </CardContent>
    </Card>
  );
};

export default MultiPeriodRateManager;
