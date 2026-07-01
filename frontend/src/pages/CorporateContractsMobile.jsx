import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import PropertySwitcher from '@/components/PropertySwitcher';
import { ArrowLeft, Building2, AlertTriangle, Calendar, DollarSign, RefreshCw, Award } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const CorporateContractsMobile = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [contracts, setContracts] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [activeView, setActiveView] = useState('contracts');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [contractsRes, customersRes, alertsRes] = await Promise.all([
        axios.get('/corporate/contracts'),
        axios.get('/corporate/customers'),
        axios.get('/corporate/alerts')
      ]);
      setContracts(contractsRes.data.contracts || []);
      setCustomers(customersRes.data.corporate_customers || []);
      setAlerts(alertsRes.data.alerts || []);
    } catch (error) {
      console.error('Failed to load corporate data:', error);
      toast.error('Kurumsal veriler yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="min-h-screen bg-gradient-to-br from-violet-50 to-indigo-50 flex items-center justify-center"><RefreshCw className="h-12 w-12 animate-spin text-violet-600" /></div>;

  return (
    <div className="min-h-screen bg-gradient-to-br from-violet-50 to-indigo-50 pb-20">
      <div className="bg-gradient-to-r from-violet-600 to-indigo-600 text-white p-4 sticky top-0 z-10 shadow-lg">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="p-2 hover:bg-white/20 rounded-lg"><ArrowLeft className="h-5 w-5" /></button>
            <div><h1 className="text-xl font-bold">Kurumsal Anlaşmalar</h1><p className="text-violet-100 text-sm">{t('nav.corporate')}</p></div>
          </div>
          <button onClick={loadData} className="p-2 hover:bg-white/20 rounded-lg"><RefreshCw className="h-5 w-5" /></button>
        </div>
        <div className="flex gap-2">
          {['contracts', 'customers', 'alerts'].map(view => (
            <button key={view} onClick={() => setActiveView(view)} className={`flex-1 py-2 rounded-lg text-sm ${activeView === view ? 'bg-white text-violet-600' : 'bg-white/20'}`}>
              {view === 'contracts' ? 'Anlaşmalar' : view === 'customers' ? 'Müşteriler' : 'Uyarılar'}
            </button>
          ))}
        </div>
      </div>

      <div className="p-4 space-y-3">
        {activeView === 'contracts' && contracts.map(contract => (
          <Card key={contract.id} className={`border-l-4 ${contract.status === 'active' ? 'border-green-500' : 'border-amber-500'}`}>
            <CardContent className="p-4">
              <div className="flex justify-between items-start mb-3">
                <div>
                  <div className="font-bold text-lg flex items-center gap-2">
                    <Building2 className="h-5 w-5" />
                    {contract.company_name}
                  </div>
                  <div className="text-sm text-gray-600">{contract.contact_person}</div>
                </div>
                <Badge className={contract.days_until_expiry < 60 ? 'bg-amber-500 text-white' : 'bg-green-500 text-white'}>
                  {contract.days_until_expiry < 60 ? 'YAKLAŞIYOR' : 'AKTİF'}
                </Badge>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm mb-3">
                <div className="bg-violet-50 p-2 rounded">
                  <div className="text-gray-500 text-xs">Anlaşma Fiyat</div>
                  <div className="font-bold text-violet-600">₺{contract.contracted_rate}</div>
                </div>
                <div className="bg-green-50 p-2 rounded">
                  <div className="text-gray-500 text-xs">İndirim</div>
                  <div className="font-bold text-green-600">%{contract.discount_percentage}</div>
                </div>
              </div>
              <div className="text-xs space-y-1">
                <div className="flex justify-between"><span className="text-gray-600">Taahhüt:</span><span className="font-semibold">{contract.room_nights_committed} gece</span></div>
                <div className="flex justify-between"><span className="text-gray-600">Kullanılan:</span><span className="font-semibold">{contract.room_nights_used} gece</span></div>
                <div className="flex justify-between"><span className="text-gray-600">Bitiş:</span><span className={contract.days_until_expiry < 60 ? 'font-bold text-amber-600' : ''}>{contract.days_until_expiry} gün</span></div>
              </div>
              <div className="flex flex-wrap gap-1 mt-2">
                {contract.special_amenities.map((amenity, idx) => <Badge key={idx} variant="outline" className="text-xs">{amenity}</Badge>)}
              </div>
            </CardContent>
          </Card>
        ))}

        {activeView === 'customers' && customers.map((customer, idx) => (
          <Card key={idx}>
            <CardContent className="p-4">
              <div className="flex justify-between items-start mb-3">
                <div>
                  <div className="font-bold text-lg flex items-center gap-2">
                    {customer.company_name}
                    {customer.vip_status && <Award className="h-4 w-4 text-yellow-500" />}
                  </div>
                  <div className="text-sm text-gray-600">{customer.contact_person}</div>
                </div>
                <Badge className={customer.contract_status === 'active' ? 'bg-green-500 text-white' : 'bg-amber-500 text-white'}>
                  {customer.contract_status === 'active' ? 'AKTİF' : 'BİTİYOR'}
                </Badge>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="bg-blue-50 p-2 rounded">
                  <div className="text-gray-500 text-xs">Rezervasyon</div>
                  <div className="font-bold text-blue-600">{customer.total_bookings}</div>
                </div>
                <div className="bg-green-50 p-2 rounded">
                  <div className="text-gray-500 text-xs">Toplam Gelir</div>
                  <div className="font-bold text-green-600">₺{(customer.total_revenue / 1000).toFixed(0)}K</div>
                </div>
              </div>
              <div className="text-xs text-gray-500 mt-2">Son rezervasyon: {customer.last_booking}</div>
            </CardContent>
          </Card>
        ))}

        {activeView === 'alerts' && alerts.map(alert => (
          <Card key={alert.id} className={`border-l-4 ${alert.severity === 'high' ? 'border-red-500 bg-red-50' : 'border-amber-500 bg-amber-50'}`}>
            <CardContent className="p-4">
              <div className="flex justify-between items-start mb-2">
                <div>
                  <div className="font-bold flex items-center gap-2">
                    <AlertTriangle className="h-5 w-5" />
                    {alert.company}
                  </div>
                  <div className="text-sm text-gray-700 mt-1">{alert.message}</div>
                </div>
                <Badge className={alert.severity === 'high' ? 'bg-red-500 text-white' : 'bg-amber-500 text-white'}>
                  {alert.severity === 'high' ? 'ACİL' : 'ORTA'}
                </Badge>
              </div>
              <div className="bg-white p-2 rounded mt-2 text-sm">
                <div className="text-gray-600">Aksiyon:</div>
                <div className="font-semibold">{alert.action_required}</div>
              </div>
              <div className="text-xs text-gray-500 mt-2">İletişim: {alert.contact_person}</div>
            </CardContent>
          </Card>
        ))}
      </div>
      <PropertySwitcher onPropertyChange={loadData} />
    </div>
  );
};

export default CorporateContractsMobile;