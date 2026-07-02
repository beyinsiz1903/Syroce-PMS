import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { ArrowLeftRight, CheckCircle, XCircle, AlertTriangle, RefreshCw, Plus, Trash2, ShieldCheck, ArrowLeft, Loader2, Info } from 'lucide-react';
import { useTranslation } from 'react-i18next';
const API = "";
const ENTITY_TYPE_LABELS = {
  room_type: 'Oda Tipi',
  rate_plan: 'Fiyat Planı',
  occupancy: 'Doluluk',
  meal_plan: 'Yemek Planı',
  tax_mode: 'Vergi Modu'
};
const ScoreGauge = ({
  score,
  size = 120
}) => {
  const {
    t
  } = useTranslation();
  const radius = (size - 16) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - score / 100 * circumference;
  const color = score >= 80 ? '#22c55e' : score >= 50 ? '#f59e0b' : '#ef4444';
  return <div className="relative inline-flex items-center justify-center" style={{
    width: size,
    height: size
  }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#e5e7eb" strokeWidth="8" />
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={color} strokeWidth="8" strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset} style={{
        transition: 'stroke-dashoffset 0.6s ease'
      }} />
      </svg>
      <span className="absolute text-2xl font-bold" style={{
      color
    }}>{score}</span>
    </div>;
};
const ValidationBadge = ({
  status
}) => {
  const {
    t
  } = useTranslation();
  if (status === 'valid') return <Badge className="bg-green-100 text-green-800 border-green-300" data-testid="validation-valid"><CheckCircle className="w-3 h-3 mr-1" />{t('cm.pages_MappingManager.gecerli')}</Badge>;
  if (status === 'invalid') return <Badge className="bg-red-100 text-red-800 border-red-300" data-testid="validation-invalid"><XCircle className="w-3 h-3 mr-1" />{t('cm.pages_MappingManager.gecersiz')}</Badge>;
  return <Badge className="bg-yellow-100 text-yellow-800 border-yellow-300" data-testid="validation-pending"><AlertTriangle className="w-3 h-3 mr-1" />Bekliyor</Badge>;
};
const MappingManager = ({
  user,
  tenant,
  onLogout
}) => {
  const {
    t
  } = useTranslation();
  const [connectors, setConnectors] = useState([]);
  const [selectedConnector, setSelectedConnector] = useState(null);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [validating, setValidating] = useState(false);
  const [activeEntityType, setActiveEntityType] = useState('room_type');
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [addForm, setAddForm] = useState({
    entity_type: 'room_type',
    pms_entity_id: '',
    pms_entity_name: '',
    external_entity_id: '',
    external_entity_name: ''
  });
  const headers = {
    Authorization: `Bearer ${localStorage.getItem('token')}`
  };
  const loadConnectors = useCallback(async () => {
    try {
      const res = await axios.get(`/channel-manager/v2/connectors`, {
        headers
      });
      setConnectors(res.data.connectors || []);
      if (!selectedConnector && res.data.connectors?.length > 0) {
        setSelectedConnector(res.data.connectors[0]);
      }
    } catch {
      toast.error('Connector listesi yüklenemedi');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);
  const loadReadinessReport = useCallback(async connectorId => {
    if (!connectorId) return;
    setLoading(true);
    try {
      const res = await axios.get(`/channel-manager/v2/mappings/${connectorId}/readiness-report`, {
        headers
      });
      setReport(res.data);
    } catch {
      toast.error('Hazırlık raporu yüklenemedi');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);
  useEffect(() => {
    loadConnectors();
  }, [loadConnectors]);
  useEffect(() => {
    if (selectedConnector) loadReadinessReport(selectedConnector.id);
  }, [selectedConnector, loadReadinessReport]);
  const handleValidateAll = async () => {
    if (!selectedConnector) return;
    setValidating(true);
    try {
      await axios.post(`/channel-manager/v2/mappings/${selectedConnector.id}/validate`, {}, {
        headers
      });
      toast.success('Tüm mapping\'ler doğrulandı');
      await loadReadinessReport(selectedConnector.id);
    } catch {
      toast.error('Doğrulama başarısız');
    } finally {
      setValidating(false);
    }
  };
  const handleCreateMapping = async () => {
    if (!selectedConnector || !addForm.pms_entity_id || !addForm.external_entity_id) {
      toast.error('PMS ve external entity seçimi zorunlu');
      return;
    }
    try {
      await axios.post(`/channel-manager/v2/mappings`, {
        connector_id: selectedConnector.id,
        ...addForm
      }, {
        headers
      });
      toast.success('Mapping oluşturuldu');
      setShowAddDialog(false);
      setAddForm({
        entity_type: activeEntityType,
        pms_entity_id: '',
        pms_entity_name: '',
        external_entity_id: '',
        external_entity_name: ''
      });
      await loadReadinessReport(selectedConnector.id);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Mapping oluşturulamadı');
    }
  };
  const handleDeleteMapping = async mappingId => {
    try {
      await axios.delete(`/channel-manager/v2/mappings/${mappingId}`, {
        headers
      });
      toast.success('Mapping silindi');
      await loadReadinessReport(selectedConnector.id);
    } catch {
      toast.error('Mapping silinemedi');
    }
  };
  const readiness = report?.readiness;
  const mappingsByType = report?.mappings_by_type || {};
  const pmsEntities = report?.pms_entities || {};
  const externalEntities = report?.external_entities || {};
  const supportedTypes = report?.supported_mapping_types || ['room_type', 'rate_plan'];
  const currentMappings = mappingsByType[activeEntityType] || [];
  const currentPmsOptions = activeEntityType === 'room_type' ? pmsEntities.room_types || [] : pmsEntities.rate_plans || [];
  const currentExtOptions = activeEntityType === 'room_type' ? externalEntities.room_types || [] : externalEntities.rate_plans || [];

  // Mapped entity IDs
  const mappedPmsIds = new Set(currentMappings.map(m => m.pms_entity_id));
  const mappedExtIds = new Set(currentMappings.map(m => m.external_entity_id));
  const unmappedPms = currentPmsOptions.filter(e => !mappedPmsIds.has(e.id));
  const unmappedExt = currentExtOptions.filter(e => !mappedExtIds.has(e.external_id || e.id));
  return <>
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => window.history.back()} data-testid="mapping-back-btn">
              <ArrowLeft className="w-4 h-4" />
            </Button>
            <div>
              <h1 className="text-3xl font-bold" data-testid="mapping-manager-title">{t('cm.pages_MappingManager.mapping_yonetimi')}</h1>
              <p className="text-sm text-gray-500 mt-1">{t('cm.pages_MappingManager.pms_varliklari_ile_provider_varliklari_a')}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleValidateAll} disabled={validating || !selectedConnector} data-testid="validate-all-btn">
              {validating ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <ShieldCheck className="w-4 h-4 mr-1" />}
              {t('cm.pages_MappingManager.tumunu_dogrula')}
            </Button>
            <Button size="sm" onClick={() => {
            setAddForm({
              ...addForm,
              entity_type: activeEntityType
            });
            setShowAddDialog(true);
          }} disabled={!selectedConnector} data-testid="add-mapping-btn">
              <Plus className="w-4 h-4 mr-1" /> {t('cm.pages_MappingManager.yeni_esleme')}
            </Button>
          </div>
        </div>

        {/* Connector Selector */}
        {connectors.length > 1 && <div className="flex gap-2 flex-wrap">
            {connectors.map(c => <Button key={c.id} variant={selectedConnector?.id === c.id ? 'default' : 'outline'} size="sm" onClick={() => setSelectedConnector(c)} data-testid={`connector-select-${c.id}`}>
                {c.display_name} ({c.provider})
              </Button>)}
          </div>}

        {loading ? <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div> : !report ? <Card><CardContent className="py-12 text-center text-gray-500">{t('cm.pages_MappingManager.connector_secin_veya_yeni_bir_connector_')}</CardContent></Card> : <>
            {/* Readiness Overview */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <Card className="lg:col-span-1" data-testid="readiness-card">
                <CardHeader className="pb-2">
                  <CardTitle className="text-lg">{t('cm.pages_MappingManager.senkronizasyon_hazirligi')}</CardTitle>
                  <CardDescription>Mapping tamamlanma skoru</CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col items-center gap-3">
                  <ScoreGauge score={readiness?.score || 0} />
                  <Badge className={readiness?.ready ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'} data-testid="readiness-status">
                    {readiness?.ready ? 'Senkronizasyona Hazır' : 'Hazır Değil'}
                  </Badge>
                  <div className="text-sm text-gray-500 text-center">
                    {t('cm.pages_MappingManager.toplam')} {readiness?.total_mappings || 0} {t('cm.pages_MappingManager.esleme')} {readiness?.invalid_mappings_count || 0} {t('cm.pages_MappingManager.gecersiz_04427')}
                  </div>
                </CardContent>
              </Card>

              <Card className="lg:col-span-2" data-testid="blocked-reasons-card">
                <CardHeader className="pb-2">
                  <CardTitle className="text-lg">{t('cm.pages_MappingManager.durum_ozeti')}</CardTitle>
                </CardHeader>
                <CardContent>
                  {readiness?.blocked_reasons?.length > 0 ? <div className="space-y-2">
                      <p className="text-sm font-medium text-red-600 mb-2">Engelleme Nedenleri:</p>
                      {readiness.blocked_reasons.map((reason, i) => <div key={reason.id || i} className="flex items-start gap-2 text-sm text-red-700 bg-red-50 rounded p-2" data-testid={`blocked-reason-${i}`}>
                          <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                          <span>{reason}</span>
                        </div>)}
                    </div> : <div className="flex items-center gap-2 text-green-700 bg-green-50 rounded p-3">
                      <CheckCircle className="w-5 h-5" />
                      <span className="font-medium">{t('cm.pages_MappingManager.tum_eslemeler_tamamlanmis_engel_yok')}</span>
                    </div>}
                  {/* Summary stats */}
                  <div className="grid grid-cols-2 gap-4 mt-4">
                    {readiness?.summary && Object.entries(readiness.summary).map(([type, data]) => <div key={type} className="bg-gray-50 rounded p-3">
                        <div className="text-xs text-gray-500 uppercase">{ENTITY_TYPE_LABELS[type] || type}</div>
                        <div className="flex items-baseline gap-2 mt-1">
                          <span className="text-lg font-bold">{data.mapped}</span>
                          <span className="text-sm text-gray-500">/ {data.total_pms || data.total_external || 0}</span>
                        </div>
                        {data.invalid > 0 && <span className="text-xs text-red-500">{data.invalid} {t('cm.pages_MappingManager.gecersiz_04427')}</span>}
                      </div>)}
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Mapping Types Tabs */}
            <Tabs value={activeEntityType} onValueChange={setActiveEntityType}>
              <TabsList>
                {supportedTypes.map(t => <TabsTrigger key={t} value={t} data-testid={`tab-${t}`}>
                    {ENTITY_TYPE_LABELS[t] || t}
                    {(mappingsByType[t]?.length || 0) > 0 && <Badge variant="secondary" className="ml-2 text-xs">{mappingsByType[t].length}</Badge>}
                  </TabsTrigger>)}
              </TabsList>

              {supportedTypes.map(entityType => <TabsContent key={entityType} value={entityType}>
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Active Mappings */}
                    <Card className="lg:col-span-2" data-testid={`mappings-table-${entityType}`}>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base">{t('cm.pages_MappingManager.aktif_eslemeler')}</CardTitle>
                      </CardHeader>
                      <CardContent>
                        {(mappingsByType[entityType] || []).length === 0 ? <div className="text-center py-8 text-gray-400">
                            <ArrowLeftRight className="w-10 h-10 mx-auto mb-2 opacity-40" />
                            <p className="text-sm">{t('cm.pages_MappingManager.henuz')} {ENTITY_TYPE_LABELS[entityType]} {t('cm.pages_MappingManager.eslemesi_yok')}</p>
                          </div> : <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="border-b bg-gray-50/80">
                                  <th className="text-left p-2 font-medium">PMS</th>
                                  <th className="text-center p-2 w-10"></th>
                                  <th className="text-left p-2 font-medium">External</th>
                                  <th className="text-center p-2 font-medium">{t('cm.pages_MappingManager.durum')}</th>
                                  <th className="text-right p-2 font-medium">{t('cm.pages_MappingManager.islem')}</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(mappingsByType[entityType] || []).map(m => <tr key={m.id} className="border-b hover:bg-gray-50/50 transition-colors" data-testid={`mapping-row-${m.id}`}>
                                    <td className="p-2">
                                      <div className="font-medium">{m.pms_entity_name || m.pms_entity_id}</div>
                                      <div className="text-xs text-gray-400">{m.pms_entity_id}</div>
                                    </td>
                                    <td className="text-center p-2">
                                      <ArrowLeftRight className="w-4 h-4 text-gray-300" />
                                    </td>
                                    <td className="p-2">
                                      <div className="font-medium">{m.external_entity_name || m.external_entity_id}</div>
                                      <div className="text-xs text-gray-400">{m.external_entity_id}</div>
                                    </td>
                                    <td className="text-center p-2">
                                      <ValidationBadge status={m.validation_status} />
                                    </td>
                                    <td className="text-right p-2">
                                      <Button variant="ghost" size="sm" className="text-red-500 hover:text-red-700 hover:bg-red-50" onClick={() => handleDeleteMapping(m.id)} data-testid={`delete-mapping-${m.id}`}>
                                        <Trash2 className="w-4 h-4" />
                                      </Button>
                                    </td>
                                  </tr>)}
                              </tbody>
                            </table>
                          </div>}
                        {/* Validation errors detail */}
                        {(mappingsByType[entityType] || []).some(m => m.validation_errors?.length > 0) && <div className="mt-4 space-y-2">
                            <p className="text-xs font-medium text-red-600">{t('cm.pages_MappingManager.dogrulama_hatalari')}</p>
                            {(mappingsByType[entityType] || []).filter(m => m.validation_errors?.length > 0).map(m => <div key={m.id} className="bg-red-50 rounded p-2 text-xs text-red-700">
                                <span className="font-medium">{m.pms_entity_name}:</span>
                                {m.validation_errors.map((e, i) => <div key={e.id || i} className="ml-4">- {e}</div>)}
                              </div>)}
                          </div>}
                      </CardContent>
                    </Card>

                    {/* Unmapped Entities Panel */}
                    <Card data-testid={`unmapped-panel-${entityType}`}>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base">{t('cm.pages_MappingManager.eslenmemis_varliklar')}</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        {entityType === 'room_type' || entityType === 'rate_plan' ? <>
                            {unmappedPms.length > 0 && <div>
                                <p className="text-xs font-medium text-amber-600 mb-1">PMS ({unmappedPms.length})</p>
                                {unmappedPms.map(e => <div key={e.id} className="flex items-center gap-2 text-sm bg-amber-50 rounded p-2 mb-1" data-testid={`unmapped-pms-${e.id}`}>
                                    <AlertTriangle className="w-3 h-3 text-amber-500" />
                                    <span>{e.name || e.id}</span>
                                  </div>)}
                              </div>}
                            {unmappedExt.length > 0 && <div>
                                <p className="text-xs font-medium text-blue-600 mb-1">External ({unmappedExt.length})</p>
                                {unmappedExt.map(e => <div key={e.external_id || e.id} className="flex items-center gap-2 text-sm bg-blue-50 rounded p-2 mb-1" data-testid={`unmapped-ext-${e.external_id || e.id}`}>
                                    <Info className="w-3 h-3 text-blue-500" />
                                    <span>{e.name || e.external_id || e.id}</span>
                                  </div>)}
                              </div>}
                            {unmappedPms.length === 0 && unmappedExt.length === 0 && <div className="text-center text-sm text-green-600 py-4">
                                <CheckCircle className="w-6 h-6 mx-auto mb-1" />
                                {t('cm.pages_MappingManager.tum_varliklar_eslenmis')}
                              </div>}
                          </> : <div className="text-center text-sm text-gray-400 py-4">
                            {t('cm.pages_MappingManager.bu_mapping_turu_icin_otomatik_tespit_yok')}
                            <br />{t('cm.pages_MappingManager.manuel_esleme_ekleyebilirsiniz')}
                          </div>}
                      </CardContent>
                    </Card>
                  </div>
                </TabsContent>)}
            </Tabs>
          </>}

        {/* Add Mapping Dialog */}
        <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle>{t('cm.pages_MappingManager.yeni_esleme_olustur')}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 mt-2">
              <div>
                <Label>{t('cm.pages_MappingManager.esleme_turu')}</Label>
                <select className="w-full border rounded-md p-2 mt-1" value={addForm.entity_type} onChange={e => setAddForm({
                ...addForm,
                entity_type: e.target.value
              })} data-testid="add-mapping-type">
                  {supportedTypes.map(t => <option key={t} value={t}>{ENTITY_TYPE_LABELS[t] || t}</option>)}
                </select>
              </div>
              <div>
                <Label>{t('cm.pages_MappingManager.pms_varlik')}</Label>
                {currentPmsOptions.length > 0 ? <select className="w-full border rounded-md p-2 mt-1" value={addForm.pms_entity_id} onChange={e => {
                const sel = currentPmsOptions.find(o => o.id === e.target.value);
                setAddForm({
                  ...addForm,
                  pms_entity_id: e.target.value,
                  pms_entity_name: sel?.name || e.target.value
                });
              }} data-testid="add-mapping-pms">
                    <option value="">{t('cm.pages_MappingManager.secin')}</option>
                    {currentPmsOptions.map(o => <option key={o.id} value={o.id}>{o.name || o.id}</option>)}
                  </select> : <input className="w-full border rounded-md p-2 mt-1" placeholder="PMS Entity ID" value={addForm.pms_entity_id} onChange={e => setAddForm({
                ...addForm,
                pms_entity_id: e.target.value,
                pms_entity_name: e.target.value
              })} data-testid="add-mapping-pms-input" />}
              </div>
              <div>
                <Label>{t('cm.pages_MappingManager.external_varlik')}</Label>
                {currentExtOptions.length > 0 ? <select className="w-full border rounded-md p-2 mt-1" value={addForm.external_entity_id} onChange={e => {
                const sel = currentExtOptions.find(o => (o.external_id || o.id) === e.target.value);
                setAddForm({
                  ...addForm,
                  external_entity_id: e.target.value,
                  external_entity_name: sel?.name || e.target.value
                });
              }} data-testid="add-mapping-external">
                    <option value="">{t('cm.pages_MappingManager.secin_4f7bd')}</option>
                    {currentExtOptions.map(o => <option key={o.external_id || o.id} value={o.external_id || o.id}>{o.name || o.external_id || o.id}</option>)}
                  </select> : <input className="w-full border rounded-md p-2 mt-1" placeholder="External Entity ID" value={addForm.external_entity_id} onChange={e => setAddForm({
                ...addForm,
                external_entity_id: e.target.value,
                external_entity_name: e.target.value
              })} data-testid="add-mapping-external-input" />}
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowAddDialog(false)} data-testid="add-mapping-cancel">{t('cm.pages_MappingManager.iptal')}</Button>
                <Button onClick={handleCreateMapping} data-testid="add-mapping-submit">{t('cm.pages_MappingManager.kaydet')}</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </>;
};
export default MappingManager;