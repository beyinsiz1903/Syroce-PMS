import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import PropertySwitcher from '@/components/PropertySwitcher';
import { ArrowLeft, Users, TrendingUp, Phone, Mail, Building2, RefreshCw, Award, AlertCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const SalesCRMMobile = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [customers, setCustomers] = useState([]);
  const [leads, setLeads] = useState([]);
  const [otaPricing, setOtaPricing] = useState([]);
  const [followUps, setFollowUps] = useState([]);
  const [activeView, setActiveView] = useState('customers');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [customersRes, leadsRes, otaRes, followUpsRes] = await Promise.all([
        axios.get('/sales/customers'),
        axios.get('/sales/leads'),
        axios.get('/sales/ota-pricing'),
        axios.get('/sales/follow-ups')
      ]);
      setCustomers(customersRes.data.customers || []);
      setLeads(leadsRes.data.leads || []);
      setOtaPricing(otaRes.data.ota_prices || []);
      setFollowUps(followUpsRes.data.follow_ups || []);
    } catch (error) {
      console.error('Failed to load sales data:', error);
      toast.error('Satış verileri yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  const getStageColor = (stage) => {
    const colors = { cold: 'bg-blue-500', warm: 'bg-amber-500', hot: 'bg-red-500', converted: 'bg-green-500' };
    return colors[stage] || 'bg-gray-500';
  };

  if (loading) return <div className="min-h-screen bg-gradient-to-br from-cyan-50 to-blue-50 flex items-center justify-center"><RefreshCw className="h-12 w-12 animate-spin text-cyan-600" /></div>;

  return (
    <div className="min-h-screen bg-gradient-to-br from-cyan-50 to-blue-50 pb-20">
      <div className="bg-gradient-to-r from-cyan-600 to-blue-600 text-white p-4 sticky top-0 z-10 shadow-lg">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="p-2 hover:bg-white/20 rounded-lg"><ArrowLeft className="h-5 w-5" /></button>
            <div><h1 className="text-xl font-bold">Satış & CRM</h1><p className="text-cyan-100 text-sm">Müşteri Yönetimi</p></div>
          </div>
          <button onClick={loadData} className="p-2 hover:bg-white/20 rounded-lg"><RefreshCw className="h-5 w-5" /></button>
        </div>
        <div className="flex gap-2 overflow-x-auto">
          {['customers', 'leads', 'ota', 'followups'].map(view => (
            <button key={view} onClick={() => setActiveView(view)} className={`px-3 py-1 rounded-lg text-sm whitespace-nowrap ${activeView === view ? 'bg-white text-cyan-600' : 'bg-white/20'}`}>
              {view === 'customers' ? 'Müşteriler' : view === 'leads' ? 'Lead\'ler' : view === 'ota' ? 'OTA Fiyat' : 'Takipler'}
            </button>
          ))}
        </div>
      </div>

      <div className="p-4 space-y-3">
        {activeView === 'customers' && customers.map(customer => (
          <Card key={customer.guest_id} className="hover:shadow-lg transition">
            <CardContent className="p-4">
              <div className="flex justify-between items-start mb-2">
                <div>
                  <div className="font-bold text-lg flex items-center gap-2">
                    {customer.guest_name}
                    {customer.is_vip && <Award className="h-4 w-4 text-yellow-500" />}
                  </div>
                  <div className="flex gap-2 mt-1">
                    {customer.customer_type.map(type => <Badge key={type} variant="outline" className="text-xs">{type}</Badge>)}
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-bold text-green-600">₺{(customer.total_revenue / 1000).toFixed(0)}K</div>
                  <div className="text-xs text-gray-500">{customer.total_bookings} rezervasyon</div>
                </div>
              </div>
              <div className="text-sm space-y-1 mt-3">
                <div className="flex items-center gap-2 text-gray-600"><Mail className="h-3 w-3" />{customer.email}</div>
                <div className="flex items-center gap-2 text-gray-600"><Phone className="h-3 w-3" />{customer.phone}</div>
              </div>
            </CardContent>
          </Card>
        ))}

        {activeView === 'leads' && leads.map(lead => (
          <Card key={lead.id} className="hover:shadow-lg transition">
            <CardContent className="p-4">
              <div className="flex justify-between items-start mb-2">
                <div>
                  <div className="font-bold">{lead.guest_name}</div>
                  {lead.company && <div className="text-sm text-gray-600 flex items-center gap-1"><Building2 className="h-3 w-3" />{lead.company}</div>}
                </div>
                <Badge className={`${getStageColor(lead.stage)} text-white`}>{lead.stage.toUpperCase()}</Badge>
              </div>
              <div className="text-sm text-gray-700 mb-2">{lead.notes}</div>
              <div className="flex justify-between text-xs">
                <span>Beklenen: ₺{lead.expected_revenue.toLocaleString()}</span>
                <span>{lead.expected_checkin}</span>
              </div>
            </CardContent>
          </Card>
        ))}

        {activeView === 'ota' && otaPricing.map((ota, idx) => (
          <Card key={idx}>
            <CardContent className="p-4">
              <div className="font-semibold mb-3">{ota.room_type}</div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div><span className="text-gray-500">Bizim:</span> <span className="font-bold">₺{ota.our_rate}</span></div>
                <div><span className="text-gray-500">Booking:</span> ₺{ota.booking_com}</div>
                <div><span className="text-gray-500">Expedia:</span> ₺{ota.expedia}</div>
                <div><span className="text-gray-500">Agoda:</span> ₺{ota.agoda}</div>
              </div>
              <Badge className={`mt-2 ${ota.price_position === 'lowest' ? 'bg-green-500' : 'bg-amber-500'} text-white`}>{ota.price_position}</Badge>
            </CardContent>
          </Card>
        ))}

        {activeView === 'followups' && (followUps.length === 0 ? (
          <Card><CardContent className="p-6 text-center"><AlertCircle className="h-12 w-12 text-gray-300 mx-auto mb-2" /><p className="text-gray-500">Takip gerekmeyen</p></CardContent></Card>
        ) : followUps.map(followUp => (
          <Card key={followUp.id} className="border-l-4 border-amber-500">
            <CardContent className="p-4">
              <div className="flex justify-between items-start">
                <div>
                  <div className="font-bold">{followUp.guest_name}</div>
                  <div className="text-sm text-gray-600">{followUp.company}</div>
                </div>
                <Badge variant="destructive">{followUp.days_since_update} gün</Badge>
              </div>
              <div className="text-sm mt-2">Beklenen: ₺{followUp.expected_revenue.toLocaleString()}</div>
            </CardContent>
          </Card>
        )))}
      </div>
      <PropertySwitcher onPropertyChange={loadData} />
    </div>
  );
};

export default SalesCRMMobile;