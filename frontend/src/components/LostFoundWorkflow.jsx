import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Package, ArrowRight, CheckCircle, XCircle, Clock, MapPin } from 'lucide-react';
import { toast } from 'sonner';

const LostFoundWorkflow = () => {
  const [items, setItems] = useState([]);
  const [selectedItem, setSelectedItem] = useState(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [history, setHistory] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadItems();
  }, []);

  const loadItems = async () => {
    try {
      const response = await axios.get('/housekeeping/lost-found/items');
      setItems(response.data.items || []);
    } catch (error) {
      console.error('Failed to load items:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadItemHistory = async (itemId) => {
    try {
      const response = await axios.get(`/housekeeping/lost-found/item/${itemId}/history`);
      setHistory(response.data);
    } catch (error) {
      toast.error('✗ Geçmiş yüklenemedi');
    }
  };

  const handleStatusChange = async (itemId, newStatus) => {
    const statusData = { status: newStatus };
    
    if (newStatus === 'claimed') {
      const claimedBy = prompt('Teslim alan kişi adı:');
      if (!claimedBy) return;
      statusData.claimed_by_name = claimedBy;
    }

    try {
      await axios.post('/housekeeping/lost-found/update-status', {
        item_id: itemId,
        ...statusData
      });
      toast.success('✓ Durum güncellendi');
      loadItems();
      setDetailsOpen(false);
    } catch (error) {
      toast.error('✗ Güncelleme başarısız');
    }
  };

  const handleTransfer = async (itemId) => {
    const toLocation = prompt('Transfer edilecek lokasyon:');
    if (!toLocation) return;

    try {
      await axios.post('/housekeeping/lost-found/transfer', {
        item_id: itemId,
        from_location: selectedItem.current_location || selectedItem.location_found,
        to_location: toLocation
      });
      toast.success('✓ Transfer tamamlandı');
      loadItems();
      loadItemHistory(itemId);
    } catch (error) {
      toast.error('✗ Transfer başarısız');
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'found': return 'bg-blue-500';
      case 'claimed': return 'bg-green-500';
      case 'expired': return 'bg-orange-500';
      case 'disposed': return 'bg-gray-500';
      default: return 'bg-gray-400';
    }
  };

  const getStatusLabel = (status) => {
    const labels = {
      found: 'Bulundu',
      claimed: 'Teslim Edildi',
      expired: 'Süresi Doldu',
      disposed: 'İmha Edildi'
    };
    return labels[status] || status;
  };

  const getCategoryIcon = (category) => {
    const icons = {
      electronics: '📱',
      clothing: '👔',
      jewelry: '💍',
      documents: '📄',
      other: '📦'
    };
    return icons[category] || '📦';
  };

  if (loading) {
    return <div className="text-center py-4">Yükleniyor...</div>;
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-lg">
            <span className="flex items-center">
              <Package className="w-5 h-5 mr-2" />
              Kayıp Eşya
            </span>
            <Badge className="bg-blue-500">
              {items.filter(i => i.status === 'found').length} aktif
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {items.length === 0 ? (
              <p className="text-center text-gray-500 py-8">Kayıp eşya yok</p>
            ) : (
              items.map((item) => (
                <div
                  key={item.id}
                  className="p-3 bg-gray-50 rounded-lg cursor-pointer hover:bg-gray-100"
                  onClick={() => {
                    setSelectedItem(item);
                    loadItemHistory(item.id);
                    setDetailsOpen(true);
                  }}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start space-x-3 flex-1">
                      <span className="text-2xl">{getCategoryIcon(item.category)}</span>
                      <div className="flex-1">
                        <div className="font-medium text-sm">{item.item_description}</div>
                        <div className="flex items-center space-x-2 mt-1 text-xs text-gray-500">
                          <MapPin className="w-3 h-3" />
                          <span>{item.current_location || item.location_found}</span>
                          {item.room_number && <span>• Oda {item.room_number}</span>}
                        </div>
                        <div className="text-xs text-gray-500 mt-1">
                          Bulan: {item.found_by} • {new Date(item.created_at).toLocaleDateString('tr-TR')}
                        </div>
                      </div>
                    </div>
                    <Badge className={getStatusColor(item.status)}>
                      {getStatusLabel(item.status)}
                    </Badge>
                  </div>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>

      {/* Item Details Dialog */}
      <Dialog open={detailsOpen} onOpenChange={setDetailsOpen}>
        <DialogContent className="max-w-md max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Kayıp Eşya Detayı</DialogTitle>
          </DialogHeader>
          {selectedItem && (
            <div className="space-y-4">
              {/* Item Info */}
              <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                <div className="flex items-start space-x-3">
                  <span className="text-3xl">{getCategoryIcon(selectedItem.category)}</span>
                  <div className="flex-1">
                    <div className="font-bold">{selectedItem.item_description}</div>
                    <div className="text-sm text-gray-600 mt-1">{selectedItem.notes}</div>
                  </div>
                </div>
              </div>

              {/* Current Status */}
              <div>
                <div className="text-xs text-gray-500 mb-1">Mevcut Durum</div>
                <Badge className={getStatusColor(selectedItem.status)}>
                  {getStatusLabel(selectedItem.status)}
                </Badge>
              </div>

              {/* Location */}
              <div>
                <div className="text-xs text-gray-500 mb-1">Konum</div>
                <div className="flex items-center space-x-2">
                  <MapPin className="w-4 h-4 text-gray-400" />
                  <span className="font-medium">{selectedItem.current_location || selectedItem.location_found}</span>
                </div>
              </div>

              {/* Transfer History */}
              {history && history.transfers.length > 0 && (
                <div>
                  <div className="text-xs text-gray-500 mb-2">Transfer Geçmişi</div>
                  <div className="space-y-2">
                    {history.transfers.map((transfer) => (
                      <div key={transfer.id} className="flex items-center space-x-2 text-xs p-2 bg-gray-50 rounded">
                        <ArrowRight className="w-4 h-4 text-gray-400" />
                        <span>{transfer.from_location}</span>
                        <ArrowRight className="w-3 h-3" />
                        <span className="font-medium">{transfer.to_location}</span>
                        <span className="text-gray-500 ml-auto">
                          {new Date(transfer.transferred_at).toLocaleDateString('tr-TR')}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Claimed Info */}
              {selectedItem.claimed_by_name && (
                <div className="p-2 bg-green-50 border border-green-200 rounded">
                  <div className="text-xs text-gray-600">Teslim Alan</div>
                  <div className="font-medium">{selectedItem.claimed_by_name}</div>
                  <div className="text-xs text-gray-500">
                    {new Date(selectedItem.claimed_at).toLocaleString('tr-TR')}
                  </div>
                </div>
              )}

              {/* Actions */}
              {selectedItem.status === 'found' && (
                <div className="grid grid-cols-2 gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleTransfer(selectedItem.id)}
                  >
                    <ArrowRight className="w-4 h-4 mr-1" />
                    Transfer
                  </Button>
                  <Button
                    size="sm"
                    className="bg-green-600 hover:bg-green-700"
                    onClick={() => handleStatusChange(selectedItem.id, 'claimed')}
                  >
                    <CheckCircle className="w-4 h-4 mr-1" />
                    Teslim Et
                  </Button>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
};

export default LostFoundWorkflow;
