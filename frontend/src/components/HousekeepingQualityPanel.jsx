import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { Image, RefreshCw, ShieldCheck, CheckCircle2, XCircle } from 'lucide-react';
import PhotoUploadComponent from './PhotoUploadComponent';

const emptyState = (
  <div className="flex flex-col items-center justify-center py-8 text-sm text-gray-500">
    <Image className="w-8 h-8 mb-2 text-gray-400" />
    Fotoğraf bulunamadı
  </div>
);

const HousekeepingQualityPanel = ({ rooms = [] }) => {
  const [selectedRoomId, setSelectedRoomId] = useState(rooms[0]?.id || null);
  const [roomPhotos, setRoomPhotos] = useState([]);
  const [recentPhotos, setRecentPhotos] = useState([]);
  const [loadingRoomPhotos, setLoadingRoomPhotos] = useState(false);
  const [loadingFeed, setLoadingFeed] = useState(false);
  const [qaActionLoading, setQaActionLoading] = useState({});

  useEffect(() => {
    if (rooms.length && !selectedRoomId) {
      setSelectedRoomId(rooms[0].id);
    }
  }, [rooms, selectedRoomId]);

  useEffect(() => {
    if (selectedRoomId) {
      fetchRoomPhotos(selectedRoomId);
    }
  }, [selectedRoomId]);

  useEffect(() => {
    fetchRecentPhotos();
  }, []);

  const selectedRoom = useMemo(
    () => rooms.find((room) => room.id === selectedRoomId),
    [rooms, selectedRoomId]
  );

  const handleRefresh = () => {
    if (selectedRoomId) {
      fetchRoomPhotos(selectedRoomId);
    }
    fetchRecentPhotos();
  };

  const fetchRoomPhotos = async (roomId) => {
    setLoadingRoomPhotos(true);
    try {
      const res = await axios.get('/media/list', {
        params: {
          module: 'housekeeping',
          entity_id: roomId
        }
      });
      setRoomPhotos(res.data.items || []);
    } catch (error) {
      console.error('Room photo fetch failed', error);
      toast.error('Oda fotoğrafları yüklenemedi');
    } finally {
      setLoadingRoomPhotos(false);
    }
  };

  const fetchRecentPhotos = async () => {
    setLoadingFeed(true);
    try {
      const res = await axios.get('/media/list', {
        params: {
          module: 'housekeeping'
        }
      });
      const items = res.data.items || [];
      setRecentPhotos(items.slice(0, 6));
    } catch (error) {
      console.error('Photo feed load failed', error);
    } finally {
      setLoadingFeed(false);
    }
  };

  const handleQAAction = async (mediaId, action, score) => {
    setQaActionLoading((prev) => ({ ...prev, [mediaId]: true }));
    try {
      await axios.post('/media/qa/review', {
        media_id: mediaId,
        action,
        score
      });
      toast.success(action === 'approve' ? 'Onaylandı' : 'Reddedildi');
      if (selectedRoomId) {
        fetchRoomPhotos(selectedRoomId);
      }
      fetchRecentPhotos();
    } catch (error) {
      console.error('QA action failed', error);
      toast.error('QA işlemi başarısız');
    } finally {
      setQaActionLoading((prev) => ({ ...prev, [mediaId]: false }));
    }
  };

  if (!rooms.length) {
    return null;
  }

  const qualityScore =
    roomPhotos.find(
      (photo) => photo.metadata?.photo_type === 'after' && photo.metadata?.quality_score
    )?.metadata?.quality_score ?? null;

  return (
    <Card>
      <CardHeader className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-blue-600" />
            Quality Control Studio
          </CardTitle>
          <p className="text-sm text-gray-500">
            Oda bazlı önce/sonra fotoğrafları ve kalite skorlarını izleyin
          </p>
        </div>
        <div className="flex gap-3">
          <Select value={selectedRoomId || ''} onValueChange={setSelectedRoomId}>
            <SelectTrigger className="w-48">
              <SelectValue placeholder="Oda seçin" />
            </SelectTrigger>
            <SelectContent>
              {rooms.map((room) => (
                <SelectItem key={room.id} value={room.id}>
                  Oda {room.room_number}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="icon" onClick={handleRefresh}>
            <RefreshCw className="w-4 h-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid gap-4 md:grid-cols-2">
          <PhotoUploadComponent
            roomId={selectedRoomId}
            roomNumber={selectedRoom?.room_number}
            photoType="before"
            showNotes={false}
            onUploadComplete={() => {
              fetchRoomPhotos(selectedRoomId);
              fetchRecentPhotos();
            }}
          />
          <PhotoUploadComponent
            roomId={selectedRoomId}
            roomNumber={selectedRoom?.room_number}
            photoType="after"
            onUploadComplete={() => {
              fetchRoomPhotos(selectedRoomId);
              fetchRecentPhotos();
            }}
          />
        </div>

        <div className="grid md:grid-cols-3 gap-4">
          <Card className="border-blue-100 bg-blue-50">
            <CardContent className="p-4">
              <p className="text-xs text-blue-600 font-semibold mb-2">
                Son Kalite Skoru
              </p>
              <p className="text-4xl font-bold text-blue-700">
                {qualityScore ?? '--'}
              </p>
              <p className="text-xs text-blue-500 mt-1">
                En son &quot;sonra&quot; fotoğrafından otomatik alınır
              </p>
            </CardContent>
          </Card>
          <Card className="border-green-100 bg-green-50">
            <CardContent className="p-4">
              <p className="text-xs text-green-600 font-semibold mb-2">
                Fotoğraf Sayısı
              </p>
              <p className="text-4xl font-bold text-green-700">
                {roomPhotos.length}
              </p>
              <p className="text-xs text-green-500 mt-1">
                Bu odaya ait tüm kayıtlı görüntüler
              </p>
            </CardContent>
          </Card>
          <Card className="border-gray-100 bg-gray-50">
            <CardContent className="p-4">
              <p className="text-xs text-gray-600 font-semibold mb-2">
                Son Yükleme
              </p>
              <p className="text-lg font-bold text-gray-900">
                {roomPhotos[0]
                  ? new Date(roomPhotos[0].uploaded_at).toLocaleString('tr-TR')
                  : '--'}
              </p>
              <p className="text-xs text-gray-500 mt-1">
                {roomPhotos[0]?.metadata?.captured_by || '—'}
              </p>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-gray-800">
              {selectedRoom?.room_number} Numaralı Oda Fotoğrafları
            </h4>
            <Badge variant="secondary">{roomPhotos.length} kayıt</Badge>
          </div>
          {loadingRoomPhotos ? (
            <div className="grid gap-3 md:grid-cols-3">
              <Skeleton className="h-40" />
              <Skeleton className="h-40" />
              <Skeleton className="h-40" />
            </div>
          ) : roomPhotos.length ? (
            <div className="grid gap-4 md:grid-cols-3">
              {roomPhotos.slice(0, 6).map((photo) => {
                const metadata = photo.metadata || {};
                const isPending = photo.qa_status === 'qa_pending';
                return (
                  <div
                    key={photo.id}
                    className="border rounded-lg overflow-hidden bg-white space-y-2"
                  >
                    {photo.storage_url ? (
                      <img
                        src={photo.storage_url}
                        alt={metadata.photo_type || photo.media_type}
                        className="h-32 w-full object-cover"
                      />
                    ) : (
                      emptyState
                    )}
                    <div className="px-3 pb-3 space-y-2 text-xs">
                      <div className="flex items-center justify-between">
                        <Badge variant="outline">{metadata.photo_type || photo.media_type}</Badge>
                        {metadata.quality_score && (
                          <span className="font-semibold text-blue-600">
                            {metadata.quality_score}/10
                          </span>
                        )}
                      </div>
                      <div className="space-y-1">
                        <p className="text-gray-600">
                          {photo.uploaded_at
                            ? new Date(photo.uploaded_at).toLocaleString('tr-TR')
                            : '--'}
                        </p>
                        <p className="text-gray-500 text-[11px] truncate">
                          {metadata.notes || 'Not yok'}
                        </p>
                        <p className="text-[11px] text-gray-500">
                          QA: {photo.qa_status || '—'}
                        </p>
                      </div>
                      {isPending && (
                        <div className="flex items-center gap-2">
                          <Button
                            size="xs"
                            className="flex-1 bg-green-50 text-green-700 hover:bg-green-100"
                            disabled={qaActionLoading[photo.id]}
                            onClick={() =>
                              handleQAAction(photo.id, 'approve', metadata.quality_score)
                            }
                          >
                            {qaActionLoading[photo.id] ? (
                              <RefreshCw className="w-3 h-3 animate-spin" />
                            ) : (
                              <CheckCircle2 className="w-3 h-3 mr-1" />
                            )}
                            Onayla
                          </Button>
                          <Button
                            size="xs"
                            variant="outline"
                            className="flex-1 border-red-200 text-red-600 hover:bg-red-50"
                            disabled={qaActionLoading[photo.id]}
                            onClick={() => handleQAAction(photo.id, 'reject')}
                          >
                            {qaActionLoading[photo.id] ? (
                              <RefreshCw className="w-3 h-3 animate-spin" />
                            ) : (
                              <XCircle className="w-3 h-3 mr-1" />
                            )}
                            Ret
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            emptyState
          )}
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-gray-800">
              Son 6 Fotoğraf (Tüm Otel)
            </h4>
            <Badge variant="outline">{recentPhotos.length}</Badge>
          </div>
          {loadingFeed ? (
            <div className="grid gap-3 md:grid-cols-6">
              {Array.from({ length: 6 }).map((_, idx) => (
                <Skeleton key={idx} className="h-32" />
              ))}
            </div>
          ) : recentPhotos.length ? (
            <div className="grid gap-3 md:grid-cols-6">
              {recentPhotos.map((photo) => (
                <div
                  key={photo.id}
                  className="border rounded-lg bg-white overflow-hidden"
                >
                  {photo.inline_preview ? (
                    <img
                      src={photo.inline_preview}
                      alt={photo.photo_type}
                      className="h-24 w-full object-cover"
                    />
                  ) : (
                    emptyState
                  )}
                  <div className="p-2 text-[11px]">
                    <p className="font-semibold">Oda {photo.room_number || '--'}</p>
                    <p className="text-gray-500 capitalize">{photo.photo_type}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            emptyState
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default HousekeepingQualityPanel;
