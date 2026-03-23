import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { CheckCircle, XCircle, Clock, DollarSign, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';

const ApprovalWidget = ({ userRole }) => {
  const [pendingApprovals, setPendingApprovals] = useState([]);
  const [myRequests, setMyRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [selectedApproval, setSelectedApproval] = useState(null);

  useEffect(() => {
    loadData();
    // Poll every 30 seconds
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    try {
      if (['admin', 'manager', 'gm'].includes(userRole)) {
        const response = await axios.get('/approvals/pending');
        setPendingApprovals(response.data.approvals || []);
      }
      
      const myResponse = await axios.get('/approvals/my-requests');
      setMyRequests(myResponse.data.approvals || []);
    } catch (error) {
      console.error('Failed to load approvals:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (approvalId) => {
    try {
      await axios.post(`/approvals/${approvalId}/approve`, {
        note: 'Onaylandı'
      });
      toast.success('✓ Talep onaylandı');
      loadData();
      setDetailsOpen(false);
    } catch (error) {
      toast.error('✗ Onaylama başarısız');
    }
  };

  const handleReject = async (approvalId) => {
    const reason = prompt('Ret nedeni:');
    if (!reason) return;

    try {
      await axios.post(`/approvals/${approvalId}/reject`, {
        reason: reason
      });
      toast.success('✓ Talep reddedildi');
      loadData();
      setDetailsOpen(false);
    } catch (error) {
      toast.error('✗ Reddetme başarısız');
    }
  };

  const getTypeIcon = (type) => {
    switch (type) {
      case 'discount': return '💰';
      case 'rate_override': return '💲';
      case 'budget': return '📊';
      case 'refund': return '↩️';
      case 'complimentary': return '🎁';
      default: return '📋';
    }
  };

  const getTypeLabel = (type) => {
    const labels = {
      discount: 'İndirim',
      rate_override: 'Fiyat Değişikliği',
      budget: 'Bütçe',
      refund: 'İade',
      complimentary: 'Complimentary'
    };
    return labels[type] || type;
  };

  const getPriorityColor = (priority) => {
    switch (priority) {
      case 'critical': return 'bg-red-500';
      case 'high': return 'bg-orange-500';
      case 'normal': return 'bg-blue-500';
      case 'low': return 'bg-gray-500';
      default: return 'bg-gray-500';
    }
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
              <Clock className="w-5 h-5 mr-2" />
              Onay Bekleyenler
            </span>
            {pendingApprovals.length > 0 && (
              <Badge className="bg-orange-500">{pendingApprovals.length}</Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {['admin', 'manager', 'gm'].includes(userRole) ? (
            <div className="space-y-2">
              {pendingApprovals.length === 0 ? (
                <p className="text-center text-gray-500 text-sm py-4">Onay bekleyen talep yok</p>
              ) : (
                pendingApprovals.slice(0, 5).map((approval) => (
                  <div
                    key={approval.id}
                    className="p-3 bg-orange-50 border border-orange-200 rounded-lg cursor-pointer hover:bg-orange-100"
                    onClick={() => {
                      setSelectedApproval(approval);
                      setDetailsOpen(true);
                    }}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-2">
                          <span className="text-xl">{getTypeIcon(approval.type)}</span>
                          <div>
                            <div className="font-medium text-sm">{getTypeLabel(approval.type)}</div>
                            <div className="text-xs text-gray-500">{approval.requested_by_name}</div>
                          </div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="font-bold text-sm">₺{approval.amount?.toFixed(0)}</div>
                        <Badge className={getPriorityColor(approval.priority)}>
                          {approval.priority}
                        </Badge>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          ) : (
            <div className="space-y-2">
              <p className="text-sm text-gray-600 mb-3">Talepleriniz:</p>
              {myRequests.length === 0 ? (
                <p className="text-center text-gray-500 text-sm py-4">Henüz talep yok</p>
              ) : (
                myRequests.slice(0, 3).map((request) => (
                  <div key={request.id} className="p-2 bg-gray-50 rounded-lg">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <span>{getTypeIcon(request.type)}</span>
                        <span className="text-sm">{getTypeLabel(request.type)}</span>
                      </div>
                      <Badge className={
                        request.status === 'approved' ? 'bg-green-500' :
                        request.status === 'rejected' ? 'bg-red-500' : 'bg-orange-500'
                      }>
                        {request.status === 'approved' ? 'Onaylandı' :
                         request.status === 'rejected' ? 'Reddedildi' : 'Bekliyor'}
                      </Badge>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Approval Details Dialog */}
      <Dialog open={detailsOpen} onOpenChange={setDetailsOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <span className="text-2xl">{selectedApproval && getTypeIcon(selectedApproval.type)}</span>
              <span>{selectedApproval && getTypeLabel(selectedApproval.type)} Talebi</span>
            </DialogTitle>
          </DialogHeader>
          {selectedApproval && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-xs text-gray-500">Talep Eden</div>
                  <div className="font-medium">{selectedApproval.requested_by_name}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-500">Tutar</div>
                  <div className="font-bold text-green-600">₺{selectedApproval.amount?.toFixed(2)}</div>
                </div>
              </div>

              <div>
                <div className="text-xs text-gray-500 mb-1">Neden</div>
                <div className="p-2 bg-gray-50 rounded text-sm">
                  {selectedApproval.reason || 'Belirtilmemiş'}
                </div>
              </div>

              <div>
                <div className="text-xs text-gray-500 mb-1">Öncelik</div>
                <Badge className={getPriorityColor(selectedApproval.priority)}>
                  {selectedApproval.priority}
                </Badge>
              </div>

              <div className="grid grid-cols-2 gap-2 pt-4">
                <Button
                  variant="outline"
                  className="border-red-500 text-red-500 hover:bg-red-50"
                  onClick={() => handleReject(selectedApproval.id)}
                >
                  <XCircle className="w-4 h-4 mr-1" />
                  Reddet
                </Button>
                <Button
                  className="bg-green-600 hover:bg-green-700"
                  onClick={() => handleApprove(selectedApproval.id)}
                >
                  <CheckCircle className="w-4 h-4 mr-1" />
                  Onayla
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
};

export default ApprovalWidget;
