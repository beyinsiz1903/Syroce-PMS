import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { TrendingUp, Users, Phone, Mail, DollarSign, CheckCircle2, XCircle, Home } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const SalesCRM = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [leads, setLeads] = useState([]);
  const [funnel, setFunnel] = useState(null);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [loading, setLoading] = useState(false);

  const [newLead, setNewLead] = useState({
    contact_name: '',
    contact_email: '',
    contact_phone: '',
    company_name: '',
    source: 'website',
    priority: 'medium',
    estimated_value: 0,
    estimated_rooms: 0,
    notes: ''
  });

  useEffect(() => {
    loadLeads();
    loadFunnel();
  }, []);

  const loadLeads = async () => {
    try {
      const response = await axios.get('/sales/leads');
      setLeads(response.data.leads || []);
    } catch (error) {
      toast.error('Lead listesi yüklenemedi');
    }
  };

  const loadFunnel = async () => {
    try {
      const response = await axios.get('/sales/funnel');
      setFunnel(response.data);
    } catch (error) {
      console.error('Funnel yüklenemedi');
    }
  };

  const handleCreateLead = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post('/sales/leads', newLead);
      toast.success('Lead başarıyla oluşturuldu!');
      setShowCreateDialog(false);
      loadLeads();
      loadFunnel();
      setNewLead({
        contact_name: '',
        contact_email: '',
        contact_phone: '',
        company_name: '',
        source: 'website',
        priority: 'medium',
        estimated_value: 0,
        estimated_rooms: 0,
        notes: ''
      });
    } catch (error) {
      toast.error('Lead oluşturulamadı');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <Button 
            variant="outline" 
            size="icon"
            onClick={() => navigate('/')}
            className="hover:bg-blue-50"
          >
            <Home className="w-5 h-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">
              📊 {t('sales.title')} & Pipeline
            </h1>
            <p className="text-gray-600">
              Satış lead'leri ve fırsat yönetimi
            </p>
          </div>
        </div>
        
        <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
          <DialogTrigger asChild>
            <Button size="lg" className="bg-blue-600 hover:bg-blue-700">
              + Yeni Lead
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Yeni Lead Oluştur</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreateLead} className="space-y-4 mt-4">
              <div>
                <Label>İlgili Kişi *</Label>
                <Input
                  value={newLead.contact_name}
                  onChange={(e) => setNewLead({...newLead, contact_name: e.target.value})}
                  required
                />
              </div>
              <div>
                <Label>E-posta *</Label>
                <Input
                  type="email"
                  value={newLead.contact_email}
                  onChange={(e) => setNewLead({...newLead, contact_email: e.target.value})}
                  required
                />
              </div>
              <div>
                <Label>Telefon</Label>
                <Input
                  value={newLead.contact_phone}
                  onChange={(e) => setNewLead({...newLead, contact_phone: e.target.value})}
                />
              </div>
              <div>
                <Label>Şirket Adı</Label>
                <Input
                  value={newLead.company_name}
                  onChange={(e) => setNewLead({...newLead, company_name: e.target.value})}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Tahmini Oda</Label>
                  <Input
                    type="number"
                    value={newLead.estimated_rooms}
                    onChange={(e) => setNewLead({...newLead, estimated_rooms: parseInt(e.target.value)})}
                  />
                </div>
                <div>
                  <Label>Tahmini Değer (€)</Label>
                  <Input
                    type="number"
                    value={newLead.estimated_value}
                    onChange={(e) => setNewLead({...newLead, estimated_value: parseFloat(e.target.value)})}
                  />
                </div>
              </div>
              <div>
                <Label>Notlar</Label>
                <Textarea
                  value={newLead.notes}
                  onChange={(e) => setNewLead({...newLead, notes: e.target.value})}
                  rows={3}
                />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? 'Oluşturuluyor...' : 'Lead Oluştur'}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Sales Funnel */}
      {funnel && (
        <div className="mb-8">
          <Card>
            <CardHeader>
              <CardTitle>Satış Hunisi</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-7 gap-2">
                {[
                  {key: 'new', label: 'Yeni', color: 'bg-gray-500'},
                  {key: 'contacted', label: 'İletişim', color: 'bg-blue-500'},
                  {key: 'qualified', label: 'Nitelikli', color: 'bg-purple-500'},
                  {key: 'proposal_sent', label: 'Teklif', color: 'bg-indigo-500'},
                  {key: 'negotiating', label: 'Müzakere', color: 'bg-orange-500'},
                  {key: 'won', label: 'Kazanıldı', color: 'bg-green-500'},
                  {key: 'lost', label: 'Kaybedildi', color: 'bg-red-500'}
                ].map((stage) => (
                  <div key={stage.key} className="text-center">
                    <div className={`${stage.color} text-white rounded-lg p-4 mb-2`}>
                      <p className="text-2xl font-bold">{funnel.funnel[stage.key]}</p>
                    </div>
                    <p className="text-xs text-gray-600">{stage.label}</p>
                  </div>
                ))}
              </div>
              <div className="mt-6 pt-6 border-t">
                <div className="flex items-center justify-between">
                  <span className="font-semibold">Win Rate:</span>
                  <span className="text-2xl font-bold text-green-600">{funnel.win_rate}%</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Lead List */}
      <div className="grid grid-cols-1 gap-4">
        {leads.map((lead) => (
          <Card key={lead.id}>
            <CardContent className="pt-6">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h3 className="text-lg font-bold">{lead.contact_name}</h3>
                  {lead.company_name && <p className="text-gray-600">{lead.company_name}</p>}
                  <div className="flex items-center gap-4 mt-2 text-sm text-gray-600">
                    <span className="flex items-center gap-1">
                      <Mail className="w-4 h-4" /> {lead.contact_email}
                    </span>
                    {lead.contact_phone && (
                      <span className="flex items-center gap-1">
                        <Phone className="w-4 h-4" /> {lead.contact_phone}
                      </span>
                    )}
                  </div>
                </div>
                <div className="text-right">
                  {lead.estimated_value > 0 && (
                    <p className="text-xl font-bold text-green-600">€{lead.estimated_value}</p>
                  )}
                  <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
                    lead.status === 'won' ? 'bg-green-100 text-green-800' :
                    lead.status === 'lost' ? 'bg-red-100 text-red-800' :
                    'bg-blue-100 text-blue-800'
                  }`}>
                    {lead.status}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};

export default SalesCRM;