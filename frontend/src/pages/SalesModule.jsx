import { useEffect, useState } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../components/ui/dialog';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import {
  Briefcase, 
  Users, 
  Building2,
  TrendingUp,
  DollarSign,
  Calendar,
  FileText,
  Target,
  Phone,
  Mail,
  CheckCircle,
  Clock,
  AlertCircle,
  Plus
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const SalesModule = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('pipeline');
  const [detailItem, setDetailItem] = useState(null);
  const [detailKind, setDetailKind] = useState('opportunity');
  const [realContracts, setRealContracts] = useState([]);
  const [contractsLoading, setContractsLoading] = useState(false);

  const loadContracts = async () => {
    try {
      setContractsLoading(true);
      const res = await axios.get('/sales/corporate-contracts');
      setRealContracts(res.data?.contracts || []);
    } catch (err) {
      console.error('Failed to load corporate contracts', err);
    } finally {
      setContractsLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'contracts') {
      loadContracts();
    }
  }, [activeTab]);

  const openDetail = (kind, item) => {
    setDetailKind(kind);
    setDetailItem(item);
  };
  const sendProposalEmail = (opp) => {
    const subject = encodeURIComponent(`Teklif: ${opp.name}`);
    const body = encodeURIComponent(
      `Sayın ${opp.contact},\n\n${opp.name} için ${opp.rooms} oda x ${opp.nights} gece, tahmini değer $${opp.value.toLocaleString()}.\n\nGiriş tarihi: ${opp.arrival}\n\nDetaylı teklifimizi ekte bulabilirsiniz.\n\nİyi günler.`,
    );
    window.location.href = `mailto:${opp.email}?subject=${subject}&body=${body}`;
  };
  const notifyComingSoon = (label) =>
    toast.info?.(`${label} ozelligi yakinda eklenecek.`) ?? toast(`${label} ozelligi yakinda eklenecek.`);

  const opportunities = [
    { 
      id: 1, 
      name: 'Tech Summit 2025', 
      company: 'ABC Tech Corp', 
      type: 'Conference', 
      rooms: 50, 
      value: 45000, 
      probability: 75,
      stage: 'Negotiation',
      arrival: '2025-03-15',
      nights: 3,
      contact: 'Sarah Johnson',
      phone: '+1-555-0123',
      email: 'sarah.j@abctech.com'
    },
    { 
      id: 2, 
      name: 'Sales Kickoff Meeting', 
      company: 'XYZ Solutions', 
      type: 'Corporate Event', 
      rooms: 30, 
      value: 28000, 
      probability: 60,
      stage: 'Proposal',
      arrival: '2025-02-20',
      nights: 2,
      contact: 'Michael Chen',
      phone: '+1-555-0124',
      email: 'm.chen@xyzsolutions.com'
    },
    { 
      id: 3, 
      name: 'Medical Conference', 
      company: 'Healthcare Alliance', 
      type: 'Conference', 
      rooms: 80, 
      value: 72000, 
      probability: 40,
      stage: 'Qualification',
      arrival: '2025-04-10',
      nights: 4,
      contact: 'Dr. Emily Rodriguez',
      phone: '+1-555-0125',
      email: 'e.rodriguez@healthcare.org'
    }
  ];

  const groupBlocks = [
    {
      id: 1,
      name: 'Wedding - Smith & Anderson',
      rooms: 25,
      blockStart: '2025-02-14',
      blockEnd: '2025-02-16',
      status: 'confirmed',
      pickup: 18,
      revenue: 22500
    },
    {
      id: 2,
      name: 'Corporate Training',
      rooms: 15,
      blockStart: '2025-02-20',
      blockEnd: '2025-02-22',
      status: 'tentative',
      pickup: 8,
      revenue: 12000
    }
  ];


  const getStageColor = (stage) => {
    const colors = {
      'Qualification': 'bg-gray-500',
      'Proposal': 'bg-blue-500',
      'Negotiation': 'bg-yellow-500',
      'Won': 'bg-green-500',
      'Lost': 'bg-red-500'
    };
    return colors[stage] || 'bg-gray-500';
  };

  const getStatusBadge = (status) => {
    const badges = {
      'confirmed': { color: 'bg-green-500', text: 'Confirmed' },
      'tentative': { color: 'bg-yellow-500', text: 'Tentative' },
      'cancelled': { color: 'bg-red-500', text: 'Cancelled' },
      'active': { color: 'bg-green-500', text: 'Active' },
      'renewal-due': { color: 'bg-amber-500', text: 'Renewal Due' }
    };
    return badges[status] || badges['confirmed'];
  };

  const getApprovalBadge = (approval) => {
    const map = {
      'draft': { color: 'bg-gray-100 text-gray-700', text: 'Taslak' },
      'pending': { color: 'bg-amber-100 text-amber-800', text: 'Onay Bekliyor' },
      'approved': { color: 'bg-emerald-100 text-emerald-800', text: 'Onaylandı' },
      'rejected': { color: 'bg-red-100 text-red-800', text: 'Reddedildi' }
    };
    return map[approval] || map['draft'];
  };

  const formatHistoryTime = (iso) => {
    if (!iso) return '-';
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleString();
  };

  return (
    <>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold" style={{ fontFamily: 'Space Grotesk' }}>
              Sales & Group Module
            </h1>
            <p className="text-gray-600 mt-1">MICE, Corporate Contracts & Group Bookings</p>
          </div>
          <div className="flex space-x-2">
            <Button onClick={() => notifyComingSoon('Yeni firsat oluşturma')}>
              <Plus className="w-4 h-4 mr-2" />
              New Opportunity
            </Button>
            <Button variant="outline" onClick={() => navigate('/pms')}>
              Back to PMS
            </Button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">Pipeline Value</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">$145,000</div>
              <div className="flex items-center text-sm text-green-600 mt-1">
                <TrendingUp className="w-4 h-4 mr-1" />
                +18% vs Last Month
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">Active Opportunities</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">12</div>
              <div className="text-sm text-gray-600 mt-1">
                160 rooms | 320 room nights
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">Group Revenue MTD</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">$54,200</div>
              <div className="text-sm text-gray-600 mt-1">
                23% of total revenue
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">Corporate Contracts</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">18</div>
              <div className="flex items-center text-sm text-amber-600 mt-1">
                <AlertCircle className="w-4 h-4 mr-1" />
                3 renewals due
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Tabs */}
        <div className="flex space-x-2 border-b">
          {[
            { id: 'pipeline', name: 'Sales Pipeline', icon: Target },
            { id: 'groups', name: 'Group Blocks', icon: Users },
            { id: 'contracts', name: 'Corporate Contracts', icon: Building2 }
          ].map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2 font-medium text-sm flex items-center space-x-2 border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-600 hover:text-gray-900'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{tab.name}</span>
              </button>
            );
          })}
        </div>

        {/* Sales Pipeline */}
        {activeTab === 'pipeline' && (
          <div className="space-y-4">
            {opportunities.map((opp) => (
              <Card key={opp.id} className="hover:shadow-lg transition-shadow">
                <CardContent className="p-6">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center space-x-3 mb-2">
                        <h3 className="text-lg font-bold">{opp.name}</h3>
                        <Badge className={getStageColor(opp.stage)}>{opp.stage}</Badge>
                        <Badge variant="outline">{opp.type}</Badge>
                      </div>
                      
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mb-4">
                        <div>
                          <div className="text-gray-600">Company</div>
                          <div className="font-semibold flex items-center">
                            <Building2 className="w-4 h-4 mr-1" />
                            {opp.company}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-600">Rooms / Nights</div>
                          <div className="font-semibold">{opp.rooms} rooms × {opp.nights} nights</div>
                        </div>
                        <div>
                          <div className="text-gray-600">Value</div>
                          <div className="font-semibold text-green-600">${opp.value.toLocaleString()}</div>
                        </div>
                        <div>
                          <div className="text-gray-600">Probability</div>
                          <div className="flex items-center">
                            <div className="w-full bg-gray-200 rounded-full h-2 mr-2">
                              <div 
                                className="bg-blue-600 h-2 rounded-full" 
                                style={{ width: `${opp.probability}%` }}
                              ></div>
                            </div>
                            <span className="font-semibold">{opp.probability}%</span>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center space-x-6 text-sm text-gray-600">
                        <div className="flex items-center">
                          <Calendar className="w-4 h-4 mr-1" />
                          Arrival: {new Date(opp.arrival).toLocaleDateString()}
                        </div>
                        <div className="flex items-center">
                          <Users className="w-4 h-4 mr-1" />
                          Contact: {opp.contact}
                        </div>
                        <div className="flex items-center">
                          <Phone className="w-4 h-4 mr-1" />
                          {opp.phone}
                        </div>
                        <div className="flex items-center">
                          <Mail className="w-4 h-4 mr-1" />
                          {opp.email}
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-col space-y-2 ml-4">
                      <Button size="sm" onClick={() => openDetail('opportunity', opp)}>
                        <FileText className="w-4 h-4 mr-1" />
                        Details
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => sendProposalEmail(opp)}>
                        <Mail className="w-4 h-4 mr-1" />
                        Proposal
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => notifyComingSoon('Rezervasyona donusturme')}>
                        <CheckCircle className="w-4 h-4 mr-1" />
                        Convert
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Group Blocks */}
        {activeTab === 'groups' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {groupBlocks.map((block) => (
              <Card key={block.id}>
                <CardHeader>
                  <CardTitle className="flex items-center justify-between">
                    <span>{block.name}</span>
                    <Badge className={getStatusBadge(block.status).color}>
                      {getStatusBadge(block.status).text}
                    </Badge>
                  </CardTitle>
                  <CardDescription>
                    {new Date(block.blockStart).toLocaleDateString()} - {new Date(block.blockEnd).toLocaleDateString()}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div>
                      <div className="flex justify-between text-sm mb-2">
                        <span className="text-gray-600">Room Pickup</span>
                        <span className="font-semibold">{block.pickup} / {block.rooms}</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div 
                          className="bg-green-600 h-2 rounded-full" 
                          style={{ width: `${(block.pickup / block.rooms) * 100}%` }}
                        ></div>
                      </div>
                    </div>

                    <div className="flex justify-between items-center pt-3 border-t">
                      <div>
                        <div className="text-sm text-gray-600">Expected Revenue</div>
                        <div className="text-xl font-bold text-green-600">
                          ${block.revenue.toLocaleString()}
                        </div>
                      </div>
                      <div className="flex space-x-2">
                        <Button size="sm" variant="outline">
                          <Users className="w-4 h-4 mr-1" />
                          Rooming List
                        </Button>
                        <Button size="sm">
                          Manage
                        </Button>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Corporate Contracts */}
        {activeTab === 'contracts' && (
          <div className="space-y-4">
            {contractsLoading ? (
              <div className="py-10 text-center text-gray-500 text-sm">Yükleniyor...</div>
            ) : realContracts.length === 0 ? (
              <div className="py-10 text-center text-gray-500 text-sm">
                Henüz kurumsal sözleşme bulunmuyor.
              </div>
            ) : realContracts.map((contract) => {
              const approval = getApprovalBadge(contract.approval_status);
              return (
              <Card key={contract.id} className="hover:shadow-lg transition-shadow">
                <CardContent className="p-6">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center space-x-3 mb-3">
                        <h3 className="text-lg font-bold">{contract.company_name}</h3>
                        {contract.contract_type && (
                          <Badge variant="outline" className="capitalize">
                            {contract.contract_type}
                          </Badge>
                        )}
                        <Badge className={getStatusBadge(contract.status).color}>
                          {getStatusBadge(contract.status).text}
                        </Badge>
                        <Badge className={approval.color}>{approval.text}</Badge>
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
                        <div>
                          <div className="text-gray-600">Contract Period</div>
                          <div className="font-semibold">
                            {contract.start_date || '-'} - {contract.end_date || '-'}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-600">Negotiated Rate</div>
                          <div className="font-semibold text-blue-600">
                            {contract.negotiated_rate != null ? `${contract.negotiated_rate}/night` : '-'}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-600">YTD Usage</div>
                          <div className="font-semibold">
                            {contract.total_bookings || 0} bookings | {contract.total_room_nights || 0} nights
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-600">YTD Revenue</div>
                          <div className="font-semibold text-green-600">
                            ₺{(contract.total_revenue || 0).toLocaleString()}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-600">Contact</div>
                          <div className="font-semibold">{contract.contact_person || '-'}</div>
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-col space-y-2 ml-4">
                      <Button size="sm" onClick={() => openDetail('contract', contract)}>
                        <FileText className="w-4 h-4 mr-1" />
                        Contract
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => notifyComingSoon('Kullanim raporu')}>
                        <TrendingUp className="w-4 h-4 mr-1" />
                        Report
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );})}
          </div>
        )}
      </div>

      <Dialog open={!!detailItem} onOpenChange={(o) => !o && setDetailItem(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {detailKind === 'opportunity' ? detailItem?.name : detailItem?.company}
            </DialogTitle>
            <DialogDescription>
              {detailKind === 'opportunity' ? 'Firsat detaylari' : 'Kurumsal sozlesme detaylari'}
            </DialogDescription>
          </DialogHeader>
          {detailItem && detailKind === 'contract' ? (
            <div className="space-y-4 text-sm">
              <div className="space-y-2">
                <div className="flex justify-between border-b py-1">
                  <span className="text-gray-500">Onay Durumu</span>
                  <Badge className={getApprovalBadge(detailItem.approval_status).color}>
                    {getApprovalBadge(detailItem.approval_status).text}
                  </Badge>
                </div>
                <div className="flex justify-between border-b py-1">
                  <span className="text-gray-500">Sözleşme Durumu</span>
                  <span className="font-medium">{detailItem.status || '-'}</span>
                </div>
                <div className="flex justify-between border-b py-1">
                  <span className="text-gray-500">İletişim</span>
                  <span className="font-medium">{detailItem.contact_person || '-'}</span>
                </div>
              </div>

              <div>
                <div className="font-semibold text-gray-800 mb-2 flex items-center gap-1">
                  <Clock className="w-4 h-4" />
                  Onay Geçmişi
                </div>
                {(detailItem.approval_history || []).length === 0 ? (
                  <div className="text-gray-500 text-xs py-2">
                    Bu sözleşme için henüz onay hareketi kaydedilmemiş.
                  </div>
                ) : (
                  <ol className="relative border-l border-gray-200 ml-2 space-y-4">
                    {[...detailItem.approval_history].reverse().map((h, idx) => (
                      <li key={idx} className="ml-4">
                        <div className="absolute -left-1.5 mt-1.5 w-3 h-3 rounded-full bg-blue-500" />
                        <div className="flex items-center gap-2 flex-wrap">
                          <Badge className={getApprovalBadge(h.from_status).color}>
                            {getApprovalBadge(h.from_status).text}
                          </Badge>
                          <span className="text-gray-400">→</span>
                          <Badge className={getApprovalBadge(h.to_status).color}>
                            {getApprovalBadge(h.to_status).text}
                          </Badge>
                        </div>
                        <div className="text-xs text-gray-600 mt-1">
                          {h.by || 'Bilinmiyor'} · {formatHistoryTime(h.at)}
                        </div>
                        {h.reason && (
                          <div className="text-xs text-gray-500 mt-0.5 italic">"{h.reason}"</div>
                        )}
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </div>
          ) : detailItem ? (
            <div className="space-y-2 text-sm">
              {Object.entries(detailItem).map(([k, v]) => (
                <div key={k} className="flex justify-between border-b py-1">
                  <span className="text-gray-500 capitalize">{k}</span>
                  <span className="font-medium">{String(v)}</span>
                </div>
              ))}
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDetailItem(null)}>Kapat</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default SalesModule;
