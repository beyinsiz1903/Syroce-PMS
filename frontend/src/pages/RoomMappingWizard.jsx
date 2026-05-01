import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  ArrowLeftRight, CheckCircle, AlertTriangle, Loader2, Wand2,
  ArrowRight, ArrowLeft, Save, XCircle, ChevronDown, RotateCcw,
  Info, ShieldAlert, Eye,
} from 'lucide-react';

const ScoreBar = ({ label, value, color }) => {
  if (value === null || value === undefined) return null;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-20 text-slate-500 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(value, 100)}%` }} />
      </div>
      <span className="w-8 text-right font-medium text-slate-600">{value}%</span>
    </div>
  );
};

const ConfidenceBadge = ({ confidence, status, breakdown, warnings }) => {
  const [expanded, setExpanded] = useState(false);
  if (status === 'unmatched') {
    return <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200" data-testid="confidence-unmatched">Eslestirilmedi</Badge>;
  }

  const badgeClass = confidence >= 80
    ? 'bg-emerald-100 text-emerald-800 border-emerald-300'
    : confidence >= 60
      ? 'bg-amber-100 text-amber-800 border-amber-300'
      : 'bg-orange-100 text-orange-800 border-orange-300';

  const hasBreakdown = breakdown && (breakdown.name_similarity > 0 || breakdown.capacity_match !== null || breakdown.price_proximity !== null);

  return (
    <div className="relative">
      <Badge
        className={`${badgeClass} cursor-pointer`}
        data-testid={`confidence-${confidence >= 80 ? 'high' : confidence >= 60 ? 'medium' : 'low'}`}
        onClick={() => hasBreakdown && setExpanded(!expanded)}
      >
        {confidence}%
        {hasBreakdown && <Info className="w-3 h-3 ml-1 opacity-60" />}
      </Badge>
      {expanded && hasBreakdown && (
        <div className="absolute right-0 top-full mt-1 z-20 w-64 bg-white rounded-lg shadow-xl border p-3 space-y-2" data-testid="score-breakdown">
          <div className="text-xs font-semibold text-slate-700 mb-2">Skor Detayi</div>
          <ScoreBar label="Isim" value={breakdown.name_similarity} color="bg-blue-500" />
          {breakdown.alias_boost > 0 && (
            <ScoreBar label="Alias" value={breakdown.alias_boost} color="bg-indigo-400" />
          )}
          <ScoreBar label="Kapasite" value={breakdown.capacity_match} color="bg-emerald-500" />
          <ScoreBar label="Fiyat" value={breakdown.price_proximity} color="bg-amber-500" />
          <div className="pt-1 border-t text-xs">
            <span className="text-slate-500">Final:</span>
            <span className="font-bold ml-1 text-slate-800">{confidence}%</span>
          </div>
          {warnings && warnings.length > 0 && (
            <div className="pt-1 space-y-1">
              {warnings.map((w, i) => (
                <div key={i} className="flex items-start gap-1 text-[10px] text-orange-600">
                  <AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" />
                  <span>{w}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const STEPS = [
  { id: 'connector', label: 'Kanal Secimi', icon: '1' },
  { id: 'rooms', label: 'Oda Eslestirme', icon: '2' },
  { id: 'rates', label: 'Fiyat Plani', icon: '3' },
  { id: 'confirm', label: 'Onay & Kayıt', icon: '4' },
];

const RoomMappingWizard = ({ user, tenant, onLogout }) => {
  const [step, setStep] = useState(0);
  const [connectors, setConnectors] = useState([]);
  const [selectedConnectorId, setSelectedConnectorId] = useState('');
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [fetchResult, setFetchResult] = useState(null);

  // Room suggestions
  const [roomData, setRoomData] = useState(null);
  const [roomSelections, setRoomSelections] = useState([]);

  // Rate suggestions
  const [rateData, setRateData] = useState(null);
  const [rateSelections, setRateSelections] = useState([]);

  // Results
  const [saving, setSaving] = useState(false);
  const [results, setResults] = useState(null);

  const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` };

  // Step 1: Load connectors
  useEffect(() => {
    (async () => {
      try {
        const { data } = await axios.get('/channel-manager/v2/connectors', { headers });
        setConnectors(data.connectors || []);
      } catch {
        toast.error('Kanal listesi yüklenemedi');
      }
    })();
  }, []);

  // Step 2: Load room suggestions
  const loadRoomSuggestions = useCallback(async () => {
    if (!selectedConnectorId) return;
    setLoading(true);
    try {
      const { data } = await axios.get(
        `/channel-manager/v2/mapping-wizard/${selectedConnectorId}/suggest-rooms`,
        { headers },
      );
      setRoomData(data);
      // Initialize selections from suggestions
      setRoomSelections(
        data.suggestions.map((s) => ({
          pms_entity_id: s.pms_entity_id,
          pms_entity_name: s.pms_entity_name,
          pms_room_count: s.pms_room_count || 0,
          pms_capacity: s.pms_capacity || 0,
          pms_base_price: s.pms_base_price || 0,
          external_entity_id: s.external_entity_id,
          external_entity_name: s.external_entity_name,
          confidence: s.confidence,
          status: s.status,
          score_breakdown: s.score_breakdown || null,
          warnings: s.warnings || [],
          enabled: s.status === 'auto',
        })),
      );
    } catch {
      toast.error('Oda eşleştirme onerileri yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, [selectedConnectorId]);

  // Step 3: Load rate suggestions
  const loadRateSuggestions = useCallback(async () => {
    if (!selectedConnectorId) return;
    setLoading(true);
    try {
      const { data } = await axios.get(
        `/channel-manager/v2/mapping-wizard/${selectedConnectorId}/suggest-rates`,
        { headers },
      );
      setRateData(data);
      setRateSelections(
        data.suggestions.map((s) => ({
          pms_entity_id: s.pms_entity_id,
          pms_entity_name: s.pms_entity_name,
          external_entity_id: s.external_entity_id,
          external_entity_name: s.external_entity_name,
          confidence: s.confidence,
          status: s.status,
          enabled: s.status !== 'unmatched',
        })),
      );
    } catch {
      toast.error('Fiyat plani onerileri yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, [selectedConnectorId]);

  // Fetch external data from channel provider
  const fetchExternalData = useCallback(async () => {
    if (!selectedConnectorId) return false;
    setFetching(true);
    setFetchResult(null);
    try {
      const { data } = await axios.post(
        `/channel-manager/v2/mapping-wizard/${selectedConnectorId}/fetch-external`,
        {},
        { headers },
      );
      setFetchResult(data);
      toast.success(`${data.room_types_count} oda tipi ve ${data.rate_plans_count} fiyat planı başarıyla çekildi`);
      return true;
    } catch (e) {
      const msg = e?.response?.data?.detail || 'Kanaldan veri cekilemedi';
      setFetchResult({ success: false, error: msg });
      // Don't block wizard - allow continuing with existing data
      return true;
    } finally {
      setFetching(false);
    }
  }, [selectedConnectorId]);

  const goNext = async () => {
    if (step === 0) {
      if (!selectedConnectorId) {
        toast.warning('Lutfen bir kanal seçin');
        return;
      }
      // First fetch external data from channel, then load suggestions
      await fetchExternalData();
      await loadRoomSuggestions();
      setStep(1);
    } else if (step === 1) {
      await loadRateSuggestions();
      setStep(2);
    } else if (step === 2) {
      setStep(3);
    }
  };

  const goBack = () => {
    if (step > 0) setStep(step - 1);
  };

  const updateRoomSelection = (idx, field, value) => {
    setRoomSelections((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], [field]: value };
      if (field === 'external_entity_id' && roomData) {
        const ext = roomData.external_room_types.find((e) => e.id === value);
        if (ext) next[idx].external_entity_name = ext.name;
      }
      return next;
    });
  };

  const updateRateSelection = (idx, field, value) => {
    setRateSelections((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], [field]: value };
      if (field === 'external_entity_id' && rateData) {
        const ext = rateData.external_rate_plans.find((e) => e.id === value);
        if (ext) next[idx].external_entity_name = ext.name;
      }
      return next;
    });
  };

  const handleSave = async () => {
    setSaving(true);
    const roomPairs = roomSelections
      .filter((s) => s.enabled && s.external_entity_id)
      .map(({ pms_entity_id, pms_entity_name, external_entity_id, external_entity_name }) => ({
        pms_entity_id, pms_entity_name, external_entity_id, external_entity_name,
      }));
    const ratePairs = rateSelections
      .filter((s) => s.enabled && s.external_entity_id)
      .map(({ pms_entity_id, pms_entity_name, external_entity_id, external_entity_name }) => ({
        pms_entity_id, pms_entity_name, external_entity_id, external_entity_name,
      }));

    const res = { rooms: null, rates: null };
    try {
      if (roomPairs.length > 0) {
        const { data } = await axios.post(
          `/channel-manager/v2/mapping-wizard/${selectedConnectorId}/bulk-create`,
          { entity_type: 'room_type', pairs: roomPairs },
          { headers },
        );
        res.rooms = data;
      }
      if (ratePairs.length > 0) {
        const { data } = await axios.post(
          `/channel-manager/v2/mapping-wizard/${selectedConnectorId}/bulk-create`,
          { entity_type: 'rate_plan', pairs: ratePairs },
          { headers },
        );
        res.rates = data;
      }
      setResults(res);
      const totalCreated = (res.rooms?.created || 0) + (res.rates?.created || 0);
      const totalFailed = (res.rooms?.failed || 0) + (res.rates?.failed || 0);
      if (totalFailed === 0) {
        toast.success(`${totalCreated} eşleştirme başarıyla oluşturuldu`);
      } else {
        toast.warning(`${totalCreated} başarılı, ${totalFailed} başarısız`);
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Eslestirme oluşturulamadı');
    } finally {
      setSaving(false);
    }
  };

  const selectedConnector = connectors.find((c) => c.id === selectedConnectorId);
  const enabledRooms = roomSelections.filter((s) => s.enabled && s.external_entity_id).length;
  const enabledRates = rateSelections.filter((s) => s.enabled && s.external_entity_id).length;

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout}>
      <div className="max-w-5xl mx-auto space-y-6" data-testid="room-mapping-wizard">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-[#C09D63]/10 flex items-center justify-center">
            <Wand2 className="w-5 h-5 text-[#C09D63]" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900" style={{ fontFamily: 'Manrope, sans-serif' }}>
              Oda Eslestirme Sihirbazi
            </h1>
            <p className="text-sm text-slate-500">PMS oda tiplerini kanal oda tiplerine otomatik eslestirin</p>
          </div>
        </div>

        {/* Stepper */}
        <div className="flex items-center gap-2" data-testid="wizard-stepper">
          {STEPS.map((s, i) => (
            <div key={s.id} className="flex items-center gap-2">
              <div
                className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-all ${
                  i === step
                    ? 'bg-[#C09D63] text-white shadow-md'
                    : i < step
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-slate-100 text-slate-400'
                }`}
              >
                {i < step ? <CheckCircle className="w-4 h-4" /> : <span className="w-4 text-center">{s.icon}</span>}
                <span className="hidden sm:inline">{s.label}</span>
              </div>
              {i < STEPS.length - 1 && <ArrowRight className="w-4 h-4 text-slate-300" />}
            </div>
          ))}
        </div>

        {/* Step Content */}
        {step === 0 && (
          <Card data-testid="step-connector">
            <CardHeader>
              <CardTitle className="text-lg" style={{ fontFamily: 'Manrope, sans-serif' }}>
                Kanal Secimi
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-slate-600">
                Eslestirme yapmak istediginiz kanal baglantisinii seçin. Sistem, PMS oda tiplerinizi kanal oda tipleriyle otomatik olarak eşleştirmeye calisacaktir.
              </p>
              <Select value={selectedConnectorId} onValueChange={setSelectedConnectorId}>
                <SelectTrigger className="w-full max-w-md" data-testid="connector-select">
                  <SelectValue placeholder="Kanal seçin..." />
                </SelectTrigger>
                <SelectContent>
                  {connectors.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      <span className="flex items-center gap-2">
                        <Badge variant="outline" className="text-xs">
                          {c.provider}
                        </Badge>
                        {c.display_name}
                        <Badge variant={c.status === 'active' ? 'default' : 'secondary'} className="text-xs ml-2">
                          {c.status}
                        </Badge>
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedConnector && (
                <div className="mt-4 p-3 bg-slate-50 rounded-lg border border-slate-100">
                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div>
                      <span className="text-slate-500">Saglayici:</span>
                      <p className="font-medium">{selectedConnector.provider}</p>
                    </div>
                    <div>
                      <span className="text-slate-500">Durum:</span>
                      <p className="font-medium">{selectedConnector.status}</p>
                    </div>
                    <div>
                      <span className="text-slate-500">Property:</span>
                      <p className="font-medium">{selectedConnector.property_id || '-'}</p>
                    </div>
                  </div>
                  <p className="text-xs text-slate-400 mt-3">
                    İleri butonuna tikladiginizda, kanal saglayicisinin API'sinden gerçek oda tipleri ve fiyat planlari otomatik olarak cekilecektir.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {step === 1 && (
          <Card data-testid="step-rooms">
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-lg" style={{ fontFamily: 'Manrope, sans-serif' }}>
                  Oda Tipi Eslestirme
                </CardTitle>
                <p className="text-sm text-slate-500 mt-1">
                  Sistem, isim benzerligi, kapasite ve fiyat sinyallerine göre otomatik eşleştirme onerdi. Düşük guvenli oneriler inceleme bolumunde listelenir.
                </p>
              </div>
              {roomData?.summary && (
                <div className="flex gap-2 flex-wrap">
                  <Badge className="bg-emerald-100 text-emerald-800">{roomData.summary.auto_matched} Otomatik</Badge>
                  <Badge className="bg-amber-100 text-amber-800">{roomData.summary.needs_review} Inceleme</Badge>
                  <Badge className="bg-red-100 text-red-800">{roomData.summary.unmatched} Eslesmedi</Badge>
                  {(roomData.summary.conflicts || 0) > 0 && (
                    <Badge className="bg-red-500 text-white animate-pulse">{roomData.summary.conflicts} Cakisma</Badge>
                  )}
                </div>
              )}
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-6 h-6 animate-spin text-[#C09D63]" />
                  <span className="ml-2 text-slate-500">Oneriler hesaplaniyor...</span>
                </div>
              ) : (
                <div className="space-y-3">
                  {/* Fetch result warning */}
                  {fetchResult && !fetchResult.success && (
                    <div className="flex items-center gap-3 p-3 bg-amber-50 rounded-lg border border-amber-200 mb-4" data-testid="fetch-warning">
                      <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
                      <div>
                        <p className="text-sm font-medium text-amber-900">Kanal verileri cekilemedi</p>
                        <p className="text-xs text-amber-700 mt-1">{fetchResult.error}</p>
                        <p className="text-xs text-amber-600 mt-1">Connector kimlik bilgilerini kontrol edin veya kanaldan oda tiplerini manuel olarak ekleyin.</p>
                      </div>
                    </div>
                  )}
                  {fetchResult?.success && (
                    <div className="flex items-center gap-3 p-3 bg-emerald-50 rounded-lg border border-emerald-200 mb-4" data-testid="fetch-success">
                      <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0" />
                      <p className="text-sm text-emerald-800">
                        Kanaldan <strong>{fetchResult.room_types_count}</strong> oda tipi ve <strong>{fetchResult.rate_plans_count}</strong> fiyat plani cekildi.
                      </p>
                    </div>
                  )}

                  {/* Already mapped */}
                  {roomData?.already_mapped?.length > 0 && (
                    <div className="mb-4">
                      <p className="text-sm font-medium text-slate-600 mb-2">Mevcut Eslestirmeler ({roomData.already_mapped.length})</p>
                      <div className="space-y-1">
                        {roomData.already_mapped.map((m, i) => (
                          <div key={i} className="flex items-center gap-3 px-3 py-2 bg-emerald-50 rounded-md text-sm">
                            <CheckCircle className="w-4 h-4 text-emerald-600" />
                            <span className="font-medium">{m.pms_entity_name}</span>
                            <ArrowLeftRight className="w-3 h-3 text-slate-400" />
                            <span>{m.external_entity_name}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {roomSelections.length === 0 && !loading && (
                    <p className="text-center text-slate-400 py-8">Eşleştirme önerisi bulunamadı</p>
                  )}

                  {roomData?.conflicts?.length > 0 && (
                    <div className="mb-4 p-3 bg-red-50 rounded-lg border border-red-200" data-testid="conflict-warnings">
                      <div className="flex items-center gap-2 mb-2">
                        <ShieldAlert className="w-4 h-4 text-red-600" />
                        <span className="text-sm font-semibold text-red-800">Cakisma Uyarilari</span>
                      </div>
                      {roomData.conflicts.map((c, i) => (
                        <div key={i} className="text-xs text-red-700 ml-6 mb-1">• {c.message}</div>
                      ))}
                    </div>
                  )}

                  {(() => {
                    const autoItems = roomSelections.filter((s) => s.status === 'auto');
                    const reviewItems = roomSelections.filter((s) => s.status === 'review');
                    const unmatchedItems = roomSelections.filter((s) => s.status === 'unmatched');

                    const renderRow = (sel, idx) => {
                      const hasWarnings = sel.warnings && sel.warnings.length > 0;
                      return (
                        <div
                          key={idx}
                          className={`p-3 rounded-lg border transition-all ${
                            hasWarnings
                              ? 'bg-orange-50/50 border-orange-200'
                              : sel.enabled ? 'bg-white border-slate-200' : 'bg-slate-50 border-slate-100 opacity-60'
                          }`}
                          data-testid={`room-suggestion-${idx}`}
                        >
                          <div className="flex items-center gap-3">
                            <input
                              type="checkbox"
                              checked={sel.enabled}
                              onChange={(e) => updateRoomSelection(idx, 'enabled', e.target.checked)}
                              className="w-4 h-4 rounded border-slate-300 text-[#C09D63] accent-[#C09D63]"
                              data-testid={`room-toggle-${idx}`}
                            />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="font-medium text-sm truncate">{sel.pms_entity_name}</span>
                                {sel.pms_room_count > 0 && (
                                  <Badge variant="outline" className="text-xs">{sel.pms_room_count} oda</Badge>
                                )}
                                {sel.pms_capacity > 0 && (
                                  <span className="text-[10px] text-slate-400">K:{sel.pms_capacity}</span>
                                )}
                                {sel.pms_base_price > 0 && (
                                  <span className="text-[10px] text-slate-400">{sel.pms_base_price.toLocaleString('tr-TR')}₺</span>
                                )}
                              </div>
                            </div>
                            <ArrowLeftRight className="w-4 h-4 text-slate-400 shrink-0" />
                            <div className="flex-1 min-w-0">
                              <Select
                                value={sel.external_entity_id || '__none__'}
                                onValueChange={(v) => updateRoomSelection(idx, 'external_entity_id', v === '__none__' ? '' : v)}
                                disabled={!sel.enabled}
                              >
                                <SelectTrigger className="w-full text-sm" data-testid={`room-ext-select-${idx}`}>
                                  <SelectValue placeholder="Kanal oda tipi seçin..." />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="__none__">-- Seçim yapilmadi --</SelectItem>
                                  {roomData?.external_room_types?.map((e) => (
                                    <SelectItem key={e.id} value={e.id}>
                                      {e.name}{e.max_occupancy > 0 ? ` (K:${e.max_occupancy})` : ''}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </div>
                            <ConfidenceBadge
                              confidence={sel.confidence}
                              status={sel.external_entity_id ? 'matched' : 'unmatched'}
                              breakdown={sel.score_breakdown}
                              warnings={sel.warnings}
                            />
                          </div>
                          {hasWarnings && (
                            <div className="mt-2 ml-7 space-y-0.5">
                              {sel.warnings.map((w, wi) => (
                                <div key={wi} className="flex items-center gap-1.5 text-[11px] text-orange-600">
                                  <AlertTriangle className="w-3 h-3 shrink-0" />
                                  <span>{w}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    };

                    return (
                      <>
                        {autoItems.length > 0 && (
                          <div className="space-y-2" data-testid="auto-section">
                            <div className="flex items-center gap-2 py-1">
                              <CheckCircle className="w-4 h-4 text-emerald-600" />
                              <span className="text-sm font-semibold text-emerald-800">Otomatik Eslestirmeler ({autoItems.length})</span>
                              <span className="text-[10px] text-slate-400">Yüksek guven — otomatik uygulanabilir</span>
                            </div>
                            {autoItems.map((sel) => renderRow(sel, roomSelections.indexOf(sel)))}
                          </div>
                        )}

                        {reviewItems.length > 0 && (
                          <div className="space-y-2 mt-4" data-testid="review-section">
                            <div className="flex items-center gap-2 py-1">
                              <Eye className="w-4 h-4 text-amber-600" />
                              <span className="text-sm font-semibold text-amber-800">Inceleme Gerektiren ({reviewItems.length})</span>
                              <span className="text-[10px] text-slate-400">Düşük guven — operator onayi gerekli</span>
                            </div>
                            {reviewItems.map((sel) => renderRow(sel, roomSelections.indexOf(sel)))}
                          </div>
                        )}

                        {unmatchedItems.length > 0 && (
                          <div className="space-y-2 mt-4" data-testid="unmatched-section">
                            <div className="flex items-center gap-2 py-1">
                              <XCircle className="w-4 h-4 text-red-500" />
                              <span className="text-sm font-semibold text-red-700">Eslesmedi ({unmatchedItems.length})</span>
                              <span className="text-[10px] text-slate-400">Kanal oda tipi bulunamadı — manuel seçim yapın</span>
                            </div>
                            {unmatchedItems.map((sel) => renderRow(sel, roomSelections.indexOf(sel)))}
                          </div>
                        )}
                      </>
                    );
                  })()}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {step === 2 && (
          <Card data-testid="step-rates">
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-lg" style={{ fontFamily: 'Manrope, sans-serif' }}>
                  Fiyat Plani Eslestirme
                </CardTitle>
                <p className="text-sm text-slate-500 mt-1">
                  Fiyat planlarini kanal fiyat planlariyla eslestirin.
                </p>
              </div>
              {rateData?.summary && (
                <div className="flex gap-2">
                  <Badge className="bg-emerald-100 text-emerald-800">{rateData.summary.auto_matched} Otomatik</Badge>
                  <Badge className="bg-amber-100 text-amber-800">{rateData.summary.needs_review} Inceleme</Badge>
                  <Badge className="bg-red-100 text-red-800">{rateData.summary.unmatched} Eslesmedi</Badge>
                </div>
              )}
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-6 h-6 animate-spin text-[#C09D63]" />
                  <span className="ml-2 text-slate-500">Oneriler hesaplaniyor...</span>
                </div>
              ) : (
                <div className="space-y-3">
                  {/* Already mapped */}
                  {rateData?.already_mapped?.length > 0 && (
                    <div className="mb-4">
                      <p className="text-sm font-medium text-slate-600 mb-2">Mevcut Eslestirmeler ({rateData.already_mapped.length})</p>
                      <div className="space-y-1">
                        {rateData.already_mapped.map((m, i) => (
                          <div key={i} className="flex items-center gap-3 px-3 py-2 bg-emerald-50 rounded-md text-sm">
                            <CheckCircle className="w-4 h-4 text-emerald-600" />
                            <span className="font-medium">{m.pms_entity_name}</span>
                            <ArrowLeftRight className="w-3 h-3 text-slate-400" />
                            <span>{m.external_entity_name}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {rateSelections.length === 0 && !loading && (
                    <p className="text-center text-slate-400 py-8">Fiyat planı önerisi bulunamadı</p>
                  )}
                  {rateSelections.map((sel, idx) => (
                    <div
                      key={idx}
                      className={`flex items-center gap-3 p-3 rounded-lg border transition-all ${
                        sel.enabled ? 'bg-white border-slate-200' : 'bg-slate-50 border-slate-100 opacity-60'
                      }`}
                      data-testid={`rate-suggestion-${idx}`}
                    >
                      <input
                        type="checkbox"
                        checked={sel.enabled}
                        onChange={(e) => updateRateSelection(idx, 'enabled', e.target.checked)}
                        className="w-4 h-4 rounded border-slate-300 text-[#C09D63] accent-[#C09D63]"
                        data-testid={`rate-toggle-${idx}`}
                      />
                      <div className="flex-1 min-w-0">
                        <span className="font-medium text-sm truncate">{sel.pms_entity_name}</span>
                      </div>
                      <ArrowLeftRight className="w-4 h-4 text-slate-400 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <Select
                          value={sel.external_entity_id || '__none__'}
                          onValueChange={(v) => updateRateSelection(idx, 'external_entity_id', v === '__none__' ? '' : v)}
                          disabled={!sel.enabled}
                        >
                          <SelectTrigger className="w-full text-sm" data-testid={`rate-ext-select-${idx}`}>
                            <SelectValue placeholder="Kanal fiyat plani seçin..." />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__none__">-- Seçim yapilmadi --</SelectItem>
                            {rateData?.external_rate_plans?.map((e) => (
                              <SelectItem key={e.id} value={e.id}>{e.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <ConfidenceBadge confidence={sel.confidence} status={sel.external_entity_id ? 'matched' : 'unmatched'} />
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {step === 3 && (
          <Card data-testid="step-confirm">
            <CardHeader>
              <CardTitle className="text-lg" style={{ fontFamily: 'Manrope, sans-serif' }}>
                Özet & Onay
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              {results ? (
                <div className="space-y-4" data-testid="wizard-results">
                  <div className="flex items-center gap-3 p-4 bg-emerald-50 rounded-lg border border-emerald-200">
                    <CheckCircle className="w-6 h-6 text-emerald-600" />
                    <div>
                      <p className="font-semibold text-emerald-900">Eslestirmeler Tamamlandi</p>
                      <p className="text-sm text-emerald-700">
                        {(results.rooms?.created || 0) + (results.rates?.created || 0)} eşleştirme oluşturuldu
                        {((results.rooms?.failed || 0) + (results.rates?.failed || 0)) > 0 &&
                          `, ${(results.rooms?.failed || 0) + (results.rates?.failed || 0)} başarısız`
                        }
                      </p>
                    </div>
                  </div>
                  {results.rooms && (
                    <div className="p-3 bg-white rounded-lg border">
                      <p className="text-sm font-medium mb-1">Oda Tipi Eslestirmeleri</p>
                      <p className="text-sm text-slate-600">
                        {results.rooms.created} oluşturuldu / {results.rooms.failed} başarısız
                      </p>
                      {results.rooms.errors?.length > 0 && (
                        <div className="mt-2 space-y-1">
                          {results.rooms.errors.map((err, i) => (
                            <p key={i} className="text-xs text-red-600 flex items-center gap-1">
                              <XCircle className="w-3 h-3" />{err.error}
                            </p>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                  {results.rates && (
                    <div className="p-3 bg-white rounded-lg border">
                      <p className="text-sm font-medium mb-1">Fiyat Plani Eslestirmeleri</p>
                      <p className="text-sm text-slate-600">
                        {results.rates.created} oluşturuldu / {results.rates.failed} başarısız
                      </p>
                      {results.rates.errors?.length > 0 && (
                        <div className="mt-2 space-y-1">
                          {results.rates.errors.map((err, i) => (
                            <p key={i} className="text-xs text-red-600 flex items-center gap-1">
                              <XCircle className="w-3 h-3" />{err.error}
                            </p>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                  <Button
                    onClick={() => { setStep(0); setResults(null); setRoomData(null); setRateData(null); setFetchResult(null); }}
                    variant="outline"
                    data-testid="wizard-restart-btn"
                  >
                    <RotateCcw className="w-4 h-4 mr-2" />
                    Yeni Eslestirme Baslat
                  </Button>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Room summary */}
                    <div className="p-4 bg-slate-50 rounded-lg border">
                      <p className="text-sm font-medium text-slate-700 mb-3">Oda Tipi Eslestirmeleri</p>
                      {roomSelections.filter((s) => s.enabled && s.external_entity_id).length === 0 ? (
                        <p className="text-sm text-slate-400">Secili eşleştirme yok</p>
                      ) : (
                        <div className="space-y-2">
                          {roomSelections.filter((s) => s.enabled && s.external_entity_id).map((s, i) => (
                            <div key={i} className="flex items-center gap-2 text-sm">
                              <CheckCircle className="w-3 h-3 text-emerald-600" />
                              <span className="font-medium">{s.pms_entity_name}</span>
                              <ArrowRight className="w-3 h-3 text-slate-400" />
                              <span>{s.external_entity_name}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                    {/* Rate summary */}
                    <div className="p-4 bg-slate-50 rounded-lg border">
                      <p className="text-sm font-medium text-slate-700 mb-3">Fiyat Plani Eslestirmeleri</p>
                      {rateSelections.filter((s) => s.enabled && s.external_entity_id).length === 0 ? (
                        <p className="text-sm text-slate-400">Secili eşleştirme yok</p>
                      ) : (
                        <div className="space-y-2">
                          {rateSelections.filter((s) => s.enabled && s.external_entity_id).map((s, i) => (
                            <div key={i} className="flex items-center gap-2 text-sm">
                              <CheckCircle className="w-3 h-3 text-emerald-600" />
                              <span className="font-medium">{s.pms_entity_name}</span>
                              <ArrowRight className="w-3 h-3 text-slate-400" />
                              <span>{s.external_entity_name}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-3 p-3 bg-amber-50 rounded-lg border border-amber-200">
                    <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
                    <p className="text-sm text-amber-800">
                      Toplam <strong>{enabledRooms + enabledRates}</strong> eşleştirme olusturulacak
                      ({enabledRooms} oda tipi + {enabledRates} fiyat plani).
                      Onayladiktan sonra eşleştirmeler aktif olarak kaydedilecektir.
                    </p>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        )}

        {/* Navigation */}
        {!results && (
          <div className="flex items-center justify-between">
            <Button
              variant="outline"
              onClick={goBack}
              disabled={step === 0}
              data-testid="wizard-back-btn"
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Geri
            </Button>
            <div className="flex items-center gap-3">
              {step === 3 ? (
                <Button
                  onClick={handleSave}
                  disabled={saving || (enabledRooms + enabledRates) === 0}
                  className="bg-[#C09D63] hover:bg-[#B08D55] text-white shadow-md"
                  data-testid="wizard-save-btn"
                >
                  {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
                  {saving ? 'Kaydediliyor...' : 'Onayla ve Kaydet'}
                </Button>
              ) : (
                <Button
                  onClick={goNext}
                  disabled={loading || fetching || (step === 0 && !selectedConnectorId)}
                  className="bg-[#C09D63] hover:bg-[#B08D55] text-white shadow-md"
                  data-testid="wizard-next-btn"
                >
                  {(loading || fetching) ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                  {fetching ? 'Kanaldan veriler cekiliyor...' : 'İleri'}
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
};

export default RoomMappingWizard;
