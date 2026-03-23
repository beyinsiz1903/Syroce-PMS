import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { AlertCircle, CheckCircle, Clock } from 'lucide-react';
import { toast } from 'sonner';

const ComplaintManager = () => {
  const [complaints, setComplaints] = useState([]);
  const [selectedComplaint, setSelectedComplaint] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadComplaints();
  }, []);

  const loadComplaints = async () => {
    try {
      const response = await axios.get('/gm/complaints');
      setComplaints(response.data.complaints || []);
    } catch (error) {
      console.error('Failed to load complaints:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleResolve = async () => {
    const resolution = prompt('Çözüm açıklaması:');
    if (!resolution) return;

    try {
      await axios.post(`/gm/complaint/${selectedComplaint.id}/resolve`, {
        resolution
      });
      toast.success('✓ Şikayet çözüldü');
      setDialogOpen(false);
      loadComplaints();
    } catch (error) {
      toast.error('✗ Hata');
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'resolved': return <CheckCircle className="w-5 h-5 text-green-500" />;
      case 'in_progress': return <Clock className="w-5 h-5 text-orange-500" />;
      default: return <AlertCircle className="w-5 h-5 text-red-500" />;
    }
  };

  const getPriorityColor = (priority) => {
    switch (priority) {
      case 'high': return 'bg-red-500';
      case 'normal': return 'bg-orange-500';
      case 'low': return 'bg-gray-500';
      default: return 'bg-gray-400';
    }
  };

  const getCategoryLabel = (category) => {
    const labels = {
      cleanliness: 'Temizlik',
      noise: 'Gürültü',
      service: 'Hizmet',
      maintenance: 'Bakım',
      food: 'Yemek'
    };
    return labels[category] || category;
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
              <AlertCircle className="w-5 h-5 mr-2" />
              Şikayetler
            </span>
            <Badge className="bg-red-500">
              {complaints.filter(c => c.status === 'open').length} açık
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {complaints.length === 0 ? (
              <p className="text-center text-gray-500 py-8">Şikayet yok</p>
            ) : (
              complaints.map((complaint) => (
                <div
                  key={complaint.id}
                  className="p-3 bg-gray-50 rounded-lg cursor-pointer hover:bg-gray-100"
                  onClick={() => {
                    setSelectedComplaint(complaint);
                    setDialogOpen(true);
                  }}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start space-x-2 flex-1">
                      {getStatusIcon(complaint.status)}
                      <div className="flex-1">
                        <div className="font-medium text-sm">{complaint.subject}</div>
                        <div className="text-xs text-gray-500 mt-1">
                          {complaint.guest_name} • Oda {complaint.room_number}
                        </div>
                        <div className="flex items-center space-x-2 mt-2">
                          <Badge className={getPriorityColor(complaint.priority)}>
                            {complaint.priority}
                          </Badge>
                          <Badge variant="outline" className="text-xs">
                            {getCategoryLabel(complaint.category)}
                          </Badge>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>

      {/* Complaint Details Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Şikayet Detayı</DialogTitle>
          </DialogHeader>
          {selectedComplaint && (
            <div className="space-y-4">
              <div>
                <div className="text-xs text-gray-500">Konu</div>
                <div className="font-bold">{selectedComplaint.subject}</div>
              </div>

              <div>
                <div className="text-xs text-gray-500">Açıklama</div>
                <div className="p-2 bg-gray-50 rounded text-sm">
                  {selectedComplaint.description}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-xs text-gray-500">Misafir</div>
                  <div className="font-medium">{selectedComplaint.guest_name}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-500">Oda</div>
                  <div className="font-medium">{selectedComplaint.room_number}</div>
                </div>
              </div>

              <div>
                <div className="text-xs text-gray-500">Atanan Departman</div>
                <div className="font-medium">{selectedComplaint.assigned_to}</div>
              </div>

              {selectedComplaint.status !== 'resolved' && (
                <Button
                  className="w-full bg-green-600 hover:bg-green-700"
                  onClick={handleResolve}
                >
                  <CheckCircle className="w-4 h-4 mr-1" />
                  Çöz
                </Button>
              )}

              {selectedComplaint.resolution && (
                <div>
                  <div className="text-xs text-gray-500">Çözüm</div>
                  <div className="p-2 bg-green-50 border border-green-200 rounded text-sm">
                    {selectedComplaint.resolution}
                  </div>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
};

export default ComplaintManager;
