import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  ArrowLeft, Search, RefreshCw, Loader2, GitBranch, CheckCircle, XCircle,
  AlertTriangle, Clock, Copy, Eye, ArrowRight, Filter
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const API = "";

const STATUS_CONFIG = {
  created: { label: 'Oluşturuldu', color: 'bg-green-100 text-green-800 border-green-300', icon: CheckCircle },
  modified: { label: 'Değiştirildi', color: 'bg-blue-100 text-blue-800 border-blue-300', icon: RefreshCw },
  cancelled: { label: 'İptal', color: 'bg-red-100 text-red-800 border-red-300', icon: XCircle },
  duplicate: { label: 'Tekrar', color: 'bg-gray-100 text-gray-800 border-gray-300', icon: Copy },
  duplicate_cancel: { label: 'Tekrar İptal', color: 'bg-gray-100 text-gray-600 border-gray-300', icon: Copy },
  conflict: { label: 'Çakışma', color: 'bg-amber-100 text-amber-800 border-amber-300', icon: AlertTriangle },
  review: { label: 'İnceleme', color: 'bg-yellow-100 text-yellow-800 border-yellow-300', icon: Eye },
  failed: { label: 'Başarısız', color: 'bg-red-100 text-red-800 border-red-300', icon: XCircle },
  out_of_order: { label: 'Sıra Dışı', color: 'bg-indigo-100 text-indigo-800 border-indigo-300', icon: AlertTriangle },
  pending: { label: 'Bekliyor', color: 'bg-yellow-100 text-yellow-800 border-yellow-300', icon: Clock },
  acknowledged: { label: 'Onaylandı', color: 'bg-green-100 text-green-800 border-green-300', icon: CheckCircle },
  dismissed: { label: 'Reddedildi', color: 'bg-gray-100 text-gray-600 border-gray-300', icon: XCircle },
  resolved: { label: 'Çözüldü', color: 'bg-green-100 text-green-800 border-green-300', icon: CheckCircle },
};

const ACK_STATUS_CONFIG = {
  ack_pending: { label: 'ACK Bekliyor', color: 'bg-yellow-50 text-yellow-700' },
  ack_sent: { label: 'ACK Gönderildi', color: 'bg-green-50 text-green-700' },
  ack_failed: { label: 'ACK Başarısız', color: 'bg-red-50 text-red-700' },
  ack_retrying: { label: 'ACK Yeniden Deneniyor', color: 'bg-blue-50 text-blue-700' },
  not_required: { label: 'ACK Gerekmiyor', color: 'bg-gray-50 text-gray-500' },
};

const StatusBadge = ({ status }) => {
  const { t } = useTranslation();
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending;
  const Icon = cfg.icon;
  return (
    <Badge className={`${cfg.color} text-xs`} data-testid={`status-badge-${status}`}>
      <Icon className="w-3 h-3 mr-1" />{cfg.label}
    </Badge>
  );
};

const AckBadge = ({ status }) => {
  const cfg = ACK_STATUS_CONFIG[status] || ACK_STATUS_CONFIG.not_required;
  return <Badge className={`${cfg.color} text-xs`} data-testid={`ack-badge-${status}`}>{cfg.label}</Badge>;
};

const ReservationLineage = ({ user, tenant, onLogout }) => {
  const [reservations, setReservations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [connectors, setConnectors] = useState([]);
  const [selectedConnector, setSelectedConnector] = useState('');
  const [selectedReservation, setSelectedReservation] = useState(null);
  const [lineageData, setLineageData] = useState(null);
  const [lineageLoading, setLineageLoading] = useState(false);
  const [stats, setStats] = useState(null);

  const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` };

  const loadConnectors = useCallback(async () => {
    try {
      const res = await axios.get(`/channel-manager/v2/connectors`, { headers });
      setConnectors(res.data.connectors || []);
    } catch { /* ignore */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  const loadReservations = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (selectedConnector) params.append('connector_id', selectedConnector);
      if (statusFilter) params.append('status', statusFilter);
      params.append('limit', '100');
      const res = await axios.get(`/channel-manager/v2/reservations/imported?${params}`, { headers });
      setReservations(res.data.reservations || []);
    } catch {
      toast.error('Rezervasyonlar yüklenemedi');
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [selectedConnector, statusFilter]);

  const loadStats = useCallback(async () => {
    try {
      const params = selectedConnector ? `?connector_id=${selectedConnector}` : '';
      const res = await axios.get(`/channel-manager/v2/reservations/stats${params}`, { headers });
      setStats(res.data);
    } catch { /* ignore */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [selectedConnector]);

  const loadLineage = async (reservationId) => {
    setLineageLoading(true);
    try {
      const res = await axios.get(`/channel-manager/v2/reservations/lineage/${reservationId}`, { headers });
      setLineageData(res.data);
    } catch {
      // Lineage endpoint may not exist yet, show single reservation
      setLineageData(null);
    } finally {
      setLineageLoading(false);
    }
  };

  useEffect(() => { loadConnectors(); }, [loadConnectors]);
  useEffect(() => { loadReservations(); loadStats(); }, [loadReservations, loadStats]);

  const filteredReservations = searchQuery
    ? reservations.filter(r =>
        (r.guest_name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
        (r.external_reservation_id || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
        (r.external_confirmation_number || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
        (r.pms_booking_id || '').toLowerCase().includes(searchQuery.toLowerCase())
      )
    : reservations;

  const openLineageModal = (reservation) => {
    setSelectedReservation(reservation);
    loadLineage(reservation.id);
  };

  return (
    <>
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => window.history.back()} data-testid="lineage-back-btn">
              <ArrowLeft className="w-4 h-4" />
            </Button>
            <div>
              <h1 className="text-3xl font-bold" data-testid="lineage-title">{t('cm.pages_ReservationLineage.rezervasyon_lineage')}</h1>
              <p className="text-sm text-gray-500 mt-1">{t('cm.pages_ReservationLineage.import_edilen_rezervasyonlarin_gecmisi_v')}</p>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => { loadReservations(); loadStats(); }} data-testid="lineage-refresh-btn">
            <RefreshCw className="w-4 h-4 mr-1" /> {t('cm.pages_ReservationLineage.yenile')}
          </Button>
        </div>

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="lineage-stats">
            <Card className="p-3">
              <div className="text-xs text-gray-500">{t('cm.pages_ReservationLineage.toplam')}</div>
              <div className="text-xl font-bold">{stats.total_reservations}</div>
            </Card>
            <Card className="p-3">
              <div className="text-xs text-green-600">{t('cm.pages_ReservationLineage.basari_orani')}</div>
              <div className="text-xl font-bold text-green-700">{stats.success_rate}%</div>
            </Card>
            <Card className="p-3">
              <div className="text-xs text-yellow-600">{t('cm.pages_ReservationLineage.inceleme_kuyrugu')}</div>
              <div className="text-xl font-bold text-yellow-700">{stats.review_queue_count}</div>
            </Card>
            <Card className="p-3">
              <div className="text-xs text-red-600">{t('cm.pages_ReservationLineage.ack_basarisiz')}</div>
              <div className="text-xl font-bold text-red-700">{stats.ack_failed_count}</div>
            </Card>
            <Card className="p-3">
              <div className="text-xs text-gray-500">{t('cm.pages_ReservationLineage.durum_dagilimi')}</div>
              <div className="flex flex-wrap gap-1 mt-1">
                {stats.by_status && Object.entries(stats.by_status).map(([s, c]) => (
                  <span key={s} className="text-[10px] bg-gray-100 rounded px-1">{s}: {c}</span>
                ))}
              </div>
            </Card>
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-wrap gap-3 items-center">
          <div className="relative flex-1 min-w-[200px] max-w-md">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <Input
              className="pl-9" placeholder={t('cm.pages_ReservationLineage.misafir_adi_external_id_pms_id_ara')}
              value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
              data-testid="lineage-search"
            />
          </div>
          <select
            className="border rounded-md p-2 text-sm"
            value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            data-testid="lineage-status-filter"
          >
            <option value="">{t('cm.pages_ReservationLineage.tum_durumlar')}</option>
            {Object.entries(STATUS_CONFIG).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
          {connectors.length > 0 && (
            <select
              className="border rounded-md p-2 text-sm"
              value={selectedConnector} onChange={e => setSelectedConnector(e.target.value)}
              data-testid="lineage-connector-filter"
            >
              <option value="">{t('cm.pages_ReservationLineage.tum_connectorlar')}</option>
              {connectors.map(c => <option key={c.id} value={c.id}>{c.display_name}</option>)}
            </select>
          )}
        </div>

        {/* Reservation List */}
        <Card data-testid="reservations-list">
          <CardContent className="p-0">
            {loading ? (
              <div className="flex justify-center py-16"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div>
            ) : filteredReservations.length === 0 ? (
              <div className="text-center py-16 text-gray-400">
                <GitBranch className="w-12 h-12 mx-auto mb-3 opacity-40" />
                <p className="font-medium">{t('cm.pages_ReservationLineage.henuz_import_edilmis_rezervasyon_yok')}</p>
                <p className="text-sm mt-1">{t('cm.pages_ReservationLineage.provider_dan_rezervasyon_cekildiginde_bu')}</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-gray-50/80 text-left">
                      <th className="p-3 font-medium">{t('cm.pages_ReservationLineage.misafir')}</th>
                      <th className="p-3 font-medium">External ID</th>
                      <th className="p-3 font-medium">Tarihler</th>
                      <th className="p-3 font-medium">Kanal</th>
                      <th className="p-3 font-medium">{t('cm.pages_ReservationLineage.durum')}</th>
                      <th className="p-3 font-medium">ACK</th>
                      <th className="p-3 font-medium">PMS ID</th>
                      <th className="p-3 font-medium text-right">{t('cm.pages_ReservationLineage.islem')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredReservations.map(r => (
                      <tr key={r.id} className="border-b hover:bg-gray-50/50 transition-colors" data-testid={`reservation-row-${r.id}`}>
                        <td className="p-3">
                          <div className="font-medium">{r.guest_name || '-'}</div>
                          <div className="text-xs text-gray-400">{r.guest_email}</div>
                        </td>
                        <td className="p-3">
                          <code className="text-xs bg-gray-100 px-1 rounded">{r.external_reservation_id || '-'}</code>
                          {r.is_modification && <Badge className="ml-1 bg-blue-50 text-blue-600 text-[10px]">Mod</Badge>}
                          {r.is_cancellation && <Badge className="ml-1 bg-red-50 text-red-600 text-[10px]">Cancel</Badge>}
                        </td>
                        <td className="p-3 text-xs">
                          {r.arrival_date ? `${r.arrival_date?.slice(0, 10)} → ${r.departure_date?.slice(0, 10)}` : '-'}
                        </td>
                        <td className="p-3"><Badge variant="outline" className="text-xs">{r.channel_name || '-'}</Badge></td>
                        <td className="p-3"><StatusBadge status={r.import_status} /></td>
                        <td className="p-3"><AckBadge status={r.ack_status} /></td>
                        <td className="p-3">
                          {r.pms_booking_id ? (
                            <code className="text-xs bg-green-50 text-green-700 px-1 rounded">{r.pms_booking_id.slice(0, 8)}...</code>
                          ) : <span className="text-xs text-gray-400">-</span>}
                        </td>
                        <td className="p-3 text-right">
                          <Button variant="ghost" size="sm" onClick={() => openLineageModal(r)} data-testid={`view-lineage-${r.id}`}>
                            <GitBranch className="w-4 h-4 mr-1" /> Detay
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Lineage Detail Modal */}
        <Dialog open={!!selectedReservation} onOpenChange={() => { setSelectedReservation(null); setLineageData(null); }}>
          <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <GitBranch className="w-5 h-5" />
                {t('cm.pages_ReservationLineage.rezervasyon_detay_lineage')}
              </DialogTitle>
            </DialogHeader>
            {selectedReservation && (
              <div className="space-y-4 mt-2">
                {/* Reservation Detail */}
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <span className="text-gray-500">{t('cm.pages_ReservationLineage.misafir_7377d')}</span>
                    <span className="ml-2 font-medium">{selectedReservation.guest_name}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">E-posta:</span>
                    <span className="ml-2">{selectedReservation.guest_email || '-'}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">External ID:</span>
                    <code className="ml-2 text-xs bg-gray-100 px-1 rounded">{selectedReservation.external_reservation_id}</code>
                  </div>
                  <div>
                    <span className="text-gray-500">Onay No:</span>
                    <span className="ml-2">{selectedReservation.external_confirmation_number || '-'}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">{t('cm.pages_ReservationLineage.giris')}</span>
                    <span className="ml-2">{selectedReservation.arrival_date?.slice(0, 10)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">{t('cm.pages_ReservationLineage.cikis')}</span>
                    <span className="ml-2">{selectedReservation.departure_date?.slice(0, 10)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">{t('cm.pages_ReservationLineage.oda_tipi_ext')}</span>
                    <span className="ml-2">{selectedReservation.room_type_external_id || '-'}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">{t('cm.pages_ReservationLineage.oda_tipi_pms')}</span>
                    <span className="ml-2">{selectedReservation.room_type_mapped_id || '-'}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">{t('cm.pages_ReservationLineage.tutar')}</span>
                    <span className="ml-2 font-medium">{selectedReservation.total_amount} {selectedReservation.currency}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Kanal:</span>
                    <span className="ml-2">{selectedReservation.channel_name || '-'}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">{t('cm.pages_ReservationLineage.durum_6d192')}</span>
                    <span className="ml-2"><StatusBadge status={selectedReservation.import_status} /></span>
                  </div>
                  <div>
                    <span className="text-gray-500">ACK:</span>
                    <span className="ml-2"><AckBadge status={selectedReservation.ack_status} /></span>
                  </div>
                  <div>
                    <span className="text-gray-500">PMS Booking:</span>
                    <code className="ml-2 text-xs bg-gray-100 px-1 rounded">{selectedReservation.pms_booking_id || 'yok'}</code>
                  </div>
                  <div>
                    <span className="text-gray-500">Fingerprint:</span>
                    <code className="ml-2 text-xs bg-gray-100 px-1 rounded">{selectedReservation.payload_fingerprint || '-'}</code>
                  </div>
                </div>

                {/* Review info */}
                {selectedReservation.review_reason && (
                  <div className="bg-yellow-50 border border-yellow-200 rounded p-3">
                    <p className="text-sm font-medium text-yellow-800">{t('cm.pages_ReservationLineage.inceleme_nedeni')}</p>
                    <p className="text-sm text-yellow-700 mt-1">{selectedReservation.review_reason}</p>
                    {selectedReservation.suggested_action && (
                      <p className="text-xs text-yellow-600 mt-1">{t('cm.pages_ReservationLineage.onerilen_islem')} {selectedReservation.suggested_action}</p>
                    )}
                  </div>
                )}

                {/* Lineage Timeline */}
                {lineageLoading ? (
                  <div className="flex justify-center py-4"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
                ) : lineageData?.lineage?.length > 0 ? (
                  <div>
                    <p className="text-sm font-medium mb-3">{t('cm.pages_ReservationLineage.lineage_gecmisi')}</p>
                    <div className="relative border-l-2 border-gray-200 ml-3 space-y-4">
                      {lineageData.lineage.map((entry, idx) => {
                        const cfg = STATUS_CONFIG[entry.import_status] || STATUS_CONFIG.pending;
                        const Icon = cfg.icon;
                        return (
                          <div key={entry.id || idx} className="relative pl-6" data-testid={`lineage-entry-${idx}`}>
                            <div className={`absolute -left-[9px] top-1 w-4 h-4 rounded-full border-2 border-white ${entry.id === selectedReservation.id ? 'bg-blue-500' : 'bg-gray-300'}`} />
                            <div className="bg-gray-50 rounded p-3">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <StatusBadge status={entry.import_status} />
                                  {entry.is_modification && <Badge className="text-[10px] bg-blue-50 text-blue-600">Modifikasyon</Badge>}
                                  {entry.is_cancellation && <Badge className="text-[10px] bg-red-50 text-red-600">{t('cm.pages_ReservationLineage.iptal')}</Badge>}
                                </div>
                                <span className="text-xs text-gray-400">{entry.created_at ? new Date(entry.created_at).toLocaleString('tr-TR') : '-'}</span>
                              </div>
                              <div className="grid grid-cols-2 gap-2 mt-2 text-xs text-gray-600">
                                <div>Fingerprint: <code className="bg-gray-200 px-1 rounded">{entry.payload_fingerprint?.slice(0, 8) || '-'}</code></div>
                                <div>Batch: <code className="bg-gray-200 px-1 rounded">{entry.batch_id?.slice(0, 8) || '-'}</code></div>
                                {entry.pms_booking_id && <div>PMS: <code className="bg-green-100 px-1 rounded">{entry.pms_booking_id.slice(0, 8)}</code></div>}
                                {entry.error_message && <div className="col-span-2 text-red-600">{t('cm.pages_ReservationLineage.hata')} {entry.error_message}</div>}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <div className="text-center text-sm text-gray-400 py-4">
                    {t('cm.pages_ReservationLineage.bu_rezervasyon_icin_ek_lineage_verisi_bu')}
                  </div>
                )}

                {/* Timestamps */}
                <div className="text-xs text-gray-400 pt-2 border-t space-y-1">
                  <div>{t('cm.pages_ReservationLineage.olusturulma')} {selectedReservation.created_at ? new Date(selectedReservation.created_at).toLocaleString('tr-TR') : '-'}</div>
                  {selectedReservation.reviewed_at && <div>{t('cm.pages_ReservationLineage.incelenme')} {new Date(selectedReservation.reviewed_at).toLocaleString('tr-TR')}</div>}
                  {selectedReservation.reprocessed_at && <div>{t('cm.pages_ReservationLineage.yeniden_islenme')} {new Date(selectedReservation.reprocessed_at).toLocaleString('tr-TR')}</div>}
                </div>
              </div>
            )}
          </DialogContent>
        </Dialog>
      </div>
    </>
  );
};

export default ReservationLineage;
