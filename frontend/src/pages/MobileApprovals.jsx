import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import PropertySwitcher from '@/components/PropertySwitcher';
import {
  ArrowLeft, 
  CheckCircle,
  XCircle,
  Clock,
  AlertTriangle,
  TrendingUp,
  DollarSign,
  RefreshCw,
  FileText,
  History
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const MobileApprovals = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [pendingApprovals, setPendingApprovals] = useState([]);
  const [myRequests, setMyRequests] = useState([]);
  const [selectedApproval, setSelectedApproval] = useState(null);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [actionModalOpen, setActionModalOpen] = useState(false);
  const [actionType, setActionType] = useState('approve');
  const [actionNotes, setActionNotes] = useState('');
  const [rejectionReason, setRejectionReason] = useState('');
  const [activeTab, setActiveTab] = useState('pending'); // pending, my-requests

  useEffect(() => {
    loadData();
  }, [activeTab]);

  const loadData = async () => {
    try {
      setLoading(true);
      
      if (activeTab === 'pending') {
        const response = await axios.get('/approvals/pending');
        setPendingApprovals(response.data.approvals || []);
      } else {
        const response = await axios.get('/approvals/my-requests');
        setMyRequests(response.data.requests || []);
      }
    } catch (error) {
      console.error('Failed to load approvals:', error);
      toast.error('Onaylar yüklenemedi');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleApprove = async () => {
    if (!selectedApproval) return;

    try {
      await axios.put(`/approvals/${selectedApproval.id}/approve`, {
        notes: actionNotes
      });
      
      toast.success('Onay isteği onaylandı');
      setActionModalOpen(false);
      setActionNotes('');
      loadData();
    } catch (error) {
      console.error('Failed to approve:', error);
      toast.error(error.response?.data?.detail || 'Onaylama başarısız');
    }
  };

  const handleReject = async () => {
    if (!selectedApproval || !rejectionReason) {
      toast.error('Red sebebi gerekli');
      return;
    }

    try {
      await axios.put(`/approvals/${selectedApproval.id}/reject`, {
        rejection_reason: rejectionReason,
        notes: actionNotes
      });
      
      toast.success('Onay isteği reddedildi');
      setActionModalOpen(false);
      setActionNotes('');
      setRejectionReason('');
      loadData();
    } catch (error) {
      console.error('Failed to reject:', error);
      toast.error(error.response?.data?.detail || 'Reddetme başarısız');
    }
  };

  const openActionModal = (approval, type) => {
    setSelectedApproval(approval);
    setActionType(type);
    setActionModalOpen(true);
  };

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const getApprovalTypeLabel = (type) => {
    const labels = {
      discount: 'İndirim',
      price_override: 'Fiyat Değişikliği',
      budget_expense: 'Bütçe Harcama',
      rate_change: 'Oran Değişikliği',
      refund: 'İade',
      comp_room: 'Complimentary Oda'
    };
    return labels[type] || type;
  };

  const getApprovalTypeIcon = (type) => {
    switch (type) {
      case 'discount':
      case 'price_override':
        return <DollarSign className="h-5 w-5 text-green-500" />;
      case 'budget_expense':
        return <TrendingUp className="h-5 w-5 text-orange-500" />;
      case 'refund':
        return <XCircle className="h-5 w-5 text-red-500" />;
      default:
        return <FileText className="h-5 w-5 text-blue-500" />;
    }
  };

  const getStatusBadge = (status) => {
    const config = {
      pending: { label: 'Bekliyor', color: 'bg-yellow-500', icon: Clock },
      approved: { label: 'Onaylandı', color: 'bg-green-500', icon: CheckCircle },
      rejected: { label: 'Reddedildi', color: 'bg-red-500', icon: XCircle }
    };
    
    const cfg = config[status] || config.pending;
    const Icon = cfg.icon;
    
    return (
      <Badge className={`${cfg.color} text-white flex items-center gap-1`}>
        <Icon className="h-3 w-3" />
        {cfg.label}
      </Badge>
    );
  };

  const getPriorityBadge = (priority, isUrgent) => {
    if (isUrgent || priority === 'urgent') {
      return <Badge variant="destructive" className="animate-pulse">ACİL</Badge>;
    }
    if (priority === 'high') {
      return <Badge variant="default" className="bg-orange-500">Yüksek</Badge>;
    }
    return null;
  };

  const canApprove = () => {
    const allowedRoles = ['admin', 'supervisor', 'fnb_manager', 'gm', 'finance_manager'];
    if (user?.role === 'super_admin') return true;
    if (Array.isArray(user?.roles) && user.roles.includes('super_admin')) return true;
    if (allowedRoles.includes(user?.role)) return true;
    if (Array.isArray(user?.roles) && user.roles.some((r) => allowedRoles.includes(r))) return true;
    return false;
  };

  const stats = {
    pending: pendingApprovals.length,
    urgent: pendingApprovals.filter(a => a.is_urgent).length,
    my_requests: myRequests.length
  };

  if (loading && !refreshing) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-purple-50 to-pink-50 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="h-12 w-12 animate-spin text-purple-600 mx-auto mb-4" />
          <p className="text-gray-600">Onaylar yükleniyor...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 to-pink-50 pb-20">
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-600 to-pink-600 text-white p-4 sticky top-0 z-10 shadow-lg">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="p-2 hover:bg-white/20 rounded-lg transition">
              <ArrowLeft className="h-5 w-5" />
            </button>
            <div>
              <h1 className="text-xl font-bold">Onay Mekanizması</h1>
              <p className="text-purple-100 text-sm">Bekleyen Onaylar</p>
            </div>
          </div>
          
          <button
            onClick={handleRefresh}
            className="p-2 hover:bg-white/20 rounded-lg transition"
            disabled={refreshing}
          >
            <RefreshCw className={`h-5 w-5 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-2">
          <button
            onClick={() => setActiveTab('pending')}
            className={`flex-1 py-2 rounded-lg font-semibold transition ${
              activeTab === 'pending' 
                ? 'bg-white text-purple-600' 
                : 'bg-white/20 text-white'
            }`}
          >
            Bekleyen ({stats.pending})
          </button>
          <button
            onClick={() => setActiveTab('my-requests')}
            className={`flex-1 py-2 rounded-lg font-semibold transition ${
              activeTab === 'my-requests' 
                ? 'bg-white text-purple-600' 
                : 'bg-white/20 text-white'
            }`}
          >
            İsteklerim ({stats.my_requests})
          </button>
        </div>
      </div>

      {/* Urgent Alerts */}
      {stats.urgent > 0 && activeTab === 'pending' && (
        <div className="mx-4 mt-4">
          <div className="bg-red-500 text-white p-3 rounded-lg flex items-center gap-2 animate-pulse">
            <AlertTriangle className="h-5 w-5" />
            <span className="font-semibold">{stats.urgent} acil onay bekliyor!</span>
          </div>
        </div>
      )}

      {/* Approvals List */}
      <div className="p-4 space-y-3">
        {activeTab === 'pending' && (
          <>
            {pendingApprovals.length === 0 ? (
              <Card>
                <CardContent className="pt-6 text-center">
                  <CheckCircle className="h-16 w-16 text-gray-300 mx-auto mb-4" />
                  <p className="text-gray-500">Bekleyen onay bulunmuyor</p>
                </CardContent>
              </Card>
            ) : (
              pendingApprovals.map((approval) => (
                <Card 
                  key={approval.id}
                  className={`${approval.is_urgent ? 'border-2 border-red-400 shadow-lg' : ''} hover:shadow-xl transition`}
                >
                  <CardContent className="p-4">
                    <div className="flex justify-between items-start mb-3">
                      <div className="flex items-start gap-3 flex-1">
                        {getApprovalTypeIcon(approval.approval_type)}
                        <div className="flex-1">
                          <div className="font-bold text-lg">{getApprovalTypeLabel(approval.approval_type)}</div>
                          <div className="text-sm text-gray-500">
                            {approval.requested_by} • {approval.requested_by_role}
                          </div>
                        </div>
                      </div>
                      {getPriorityBadge(approval.priority, approval.is_urgent)}
                    </div>

                    <div className="bg-gray-50 rounded p-3 mb-3 space-y-1">
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-600">Miktar:</span>
                        <span className="font-bold">₺{approval.amount.toFixed(2)}</span>
                      </div>
                      {approval.original_value && (
                        <div className="flex justify-between text-sm">
                          <span className="text-gray-600">Eski → Yeni:</span>
                          <span>₺{approval.original_value} → ₺{approval.new_value}</span>
                        </div>
                      )}
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-600">Bekliyor:</span>
                        <span className={approval.is_urgent ? 'text-red-600 font-semibold' : ''}>
                          {approval.time_waiting_hours} saat
                        </span>
                      </div>
                    </div>

                    <div className="text-sm text-gray-700 mb-3">
                      <span className="font-semibold">Sebep: </span>
                      {approval.reason}
                    </div>

                    {canApprove() && (
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          onClick={() => openActionModal(approval, 'reject')}
                          variant="outline"
                          className="flex-1 border-red-200 hover:bg-red-50"
                        >
                          <XCircle className="h-4 w-4 mr-2" />
                          Reddet
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => openActionModal(approval, 'approve')}
                          className="flex-1 bg-green-600 hover:bg-green-700"
                        >
                          <CheckCircle className="h-4 w-4 mr-2" />
                          Onayla
                        </Button>
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))
            )}
          </>
        )}

        {activeTab === 'my-requests' && (
          <>
            {myRequests.length === 0 ? (
              <Card>
                <CardContent className="pt-6 text-center">
                  <FileText className="h-16 w-16 text-gray-300 mx-auto mb-4" />
                  <p className="text-gray-500">Henüz istek oluşturmadınız</p>
                </CardContent>
              </Card>
            ) : (
              myRequests.map((request) => (
                <Card key={request.id}>
                  <CardContent className="p-4">
                    <div className="flex justify-between items-start mb-3">
                      <div className="flex items-start gap-3 flex-1">
                        {getApprovalTypeIcon(request.approval_type)}
                        <div className="flex-1">
                          <div className="font-bold">{getApprovalTypeLabel(request.approval_type)}</div>
                          <div className="text-sm text-gray-500">
                            {new Date(request.request_date).toLocaleDateString('tr-TR')}
                          </div>
                        </div>
                      </div>
                      {getStatusBadge(request.status)}
                    </div>

                    <div className="text-sm space-y-1 mb-2">
                      <div className="flex justify-between">
                        <span className="text-gray-600">Miktar:</span>
                        <span className="font-semibold">₺{request.amount.toFixed(2)}</span>
                      </div>
                      <div className="text-gray-700">
                        <span className="font-semibold">Sebep: </span>
                        {request.reason}
                      </div>
                    </div>

                    {request.status === 'approved' && request.approved_by && (
                      <div className="text-xs text-green-600 bg-green-50 p-2 rounded">
                        ✓ {request.approved_by} tarafından onaylandı
                      </div>
                    )}

                    {request.status === 'rejected' && request.rejection_reason && (
                      <div className="text-xs text-red-600 bg-red-50 p-2 rounded">
                        ✗ Red: {request.rejection_reason}
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))
            )}
          </>
        )}
      </div>

      {/* Action Modal (Approve/Reject) */}
      <Dialog open={actionModalOpen} onOpenChange={setActionModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {actionType === 'approve' ? 'Onay İsteğini Onayla' : 'Onay İsteğini Reddet'}
            </DialogTitle>
          </DialogHeader>
          
          {selectedApproval && (
            <div className="space-y-4">
              <div className="bg-gray-50 p-3 rounded">
                <div className="font-semibold mb-2">{getApprovalTypeLabel(selectedApproval.approval_type)}</div>
                <div className="text-sm space-y-1">
                  <div>Talep Eden: {selectedApproval.requested_by}</div>
                  <div>Miktar: ₺{selectedApproval.amount.toFixed(2)}</div>
                  <div>Sebep: {selectedApproval.reason}</div>
                </div>
              </div>

              {actionType === 'reject' && (
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Red Sebebi <span className="text-red-500">*</span>
                  </label>
                  <Textarea
                    value={rejectionReason}
                    onChange={(e) => setRejectionReason(e.target.value)}
                    placeholder="Red sebebini belirtin..."
                    rows={3}
                  />
                </div>
              )}

              <div>
                <label className="block text-sm font-medium mb-2">Notlar (Opsiyonel)</label>
                <Textarea
                  value={actionNotes}
                  onChange={(e) => setActionNotes(e.target.value)}
                  placeholder="Ek notlar..."
                  rows={2}
                />
              </div>

              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => {
                    setActionModalOpen(false);
                    setActionNotes('');
                    setRejectionReason('');
                  }}
                  className="flex-1"
                >
                  İptal
                </Button>
                <Button
                  onClick={actionType === 'approve' ? handleApprove : handleReject}
                  className={`flex-1 ${
                    actionType === 'approve' 
                      ? 'bg-green-600 hover:bg-green-700' 
                      : 'bg-red-600 hover:bg-red-700'
                  }`}
                >
                  {actionType === 'approve' ? 'Onayla' : 'Reddet'}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Property Switcher */}
      <PropertySwitcher onPropertyChange={() => loadData()} />
    </div>
  );
};

export default MobileApprovals;
