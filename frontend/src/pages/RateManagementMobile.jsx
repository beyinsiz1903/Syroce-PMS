import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import PropertySwitcher from '@/components/PropertySwitcher';
import { ArrowLeft, DollarSign, Tag, Package, TrendingUp, RefreshCw, Percent } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const RateManagementMobile = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [campaigns, setCampaigns] = useState([]);
  const [discountCodes, setDiscountCodes] = useState([]);
  const [packages, setPackages] = useState([]);
  const [promoRates, setPromoRates] = useState([]);
  const [activeView, setActiveView] = useState('campaigns');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [campaignsRes, codesRes, packagesRes, promoRes] = await Promise.all([
        axios.get('/rates/campaigns'),
        axios.get('/rates/discount-codes'),
        axios.get('/rates/packages'),
        axios.get('/rates/promotional')
      ]);
      setCampaigns(campaignsRes.data.campaigns || []);
      setDiscountCodes(codesRes.data.discount_codes || []);
      setPackages(packagesRes.data.packages || []);
      setPromoRates(promoRes.data.promotional_rates || []);
    } catch (error) {
      console.error('Failed to load rate data:', error);
      toast.error('Fiyat verileri yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="min-h-screen bg-gradient-to-br from-amber-50 to-amber-50 flex items-center justify-center"><RefreshCw className="h-12 w-12 animate-spin text-amber-600" /></div>;

  return (
    <div className="min-h-screen bg-gradient-to-br from-amber-50 to-amber-50 pb-20">
      <div className="bg-gradient-to-r from-amber-600 to-amber-600 text-white p-4 sticky top-0 z-10 shadow-lg">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="p-2 hover:bg-white/20 rounded-lg"><ArrowLeft className="h-5 w-5" /></button>
            <div><h1 className="text-xl font-bold">Fiyat Yönetimi</h1><p className="text-amber-100 text-sm">Kampanya & İndirim</p></div>
          </div>
          <button onClick={loadData} className="p-2 hover:bg-white/20 rounded-lg"><RefreshCw className="h-5 w-5" /></button>
        </div>
        <div className="flex gap-2 overflow-x-auto">
          {['campaigns', 'codes', 'packages', 'promo'].map(view => (
            <button key={view} onClick={() => setActiveView(view)} className={`px-3 py-1 rounded-lg text-sm whitespace-nowrap ${activeView === view ? 'bg-white text-amber-600' : 'bg-white/20'}`}>
              {view === 'campaigns' ? 'Kampanyalar' : view === 'codes' ? 'Kodlar' : view === 'packages' ? 'Paketler' : 'Promosyon'}
            </button>
          ))}
        </div>
      </div>

      <div className="p-4 space-y-3">
        {activeView === 'campaigns' && campaigns.map(campaign => (
          <Card key={campaign.id} className="hover:shadow-lg transition">
            <CardContent className="p-4">
              <div className="flex justify-between items-start mb-3">
                <div>
                  <div className="font-bold text-lg">{campaign.name}</div>
                  <div className="text-sm text-gray-600">{campaign.description}</div>
                </div>
                <Badge className="bg-green-500 text-white">AKTİF</Badge>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="bg-amber-50 p-2 rounded">
                  <div className="text-gray-500 text-xs">İndirim</div>
                  <div className="font-bold">{campaign.discount_type === 'percentage' ? `%${campaign.discount_value}` : `₺${campaign.discount_value}`}</div>
                </div>
                <div className="bg-green-50 p-2 rounded">
                  <div className="text-gray-500 text-xs">Rezervasyon</div>
                  <div className="font-bold">{campaign.bookings_count}</div>
                </div>
              </div>
              <div className="text-sm text-green-600 font-semibold mt-2">Gelir: ₺{campaign.revenue_generated.toLocaleString()}</div>
            </CardContent>
          </Card>
        ))}

        {activeView === 'codes' && discountCodes.map(code => (
          <Card key={code.id}>
            <CardContent className="p-4">
              <div className="flex justify-between items-start mb-2">
                <div>
                  <div className="font-bold text-lg font-mono">{code.code}</div>
                  <div className="text-sm text-gray-600">{code.description}</div>
                </div>
                <Tag className="h-5 w-5 text-amber-600" />
              </div>
              <div className="flex justify-between items-center text-sm mt-3">
                <span className="font-semibold">{code.discount_type === 'percentage' ? `%${code.discount_value}` : `₺${code.discount_value}`}</span>
                <span className="text-gray-500">{code.usage_count}/{code.usage_limit} kullanım</span>
              </div>
            </CardContent>
          </Card>
        ))}

        {activeView === 'packages' && packages.map(pkg => (
          <Card key={pkg.id}>
            <CardContent className="p-4">
              <div className="flex justify-between items-start mb-2">
                <div>
                  <div className="font-bold text-lg">{pkg.name}</div>
                  <div className="text-sm text-gray-600">{pkg.description}</div>
                </div>
                <div className="text-2xl font-bold text-amber-600">₺{pkg.base_rate}</div>
              </div>
              <div className="flex flex-wrap gap-2 mt-3">
                {pkg.inclusions.map((inc, idx) => <Badge key={idx} variant="outline" className="text-xs">{inc}</Badge>)}
              </div>
              <div className="text-sm text-gray-500 mt-2">{pkg.bookings_count} rezervasyon</div>
            </CardContent>
          </Card>
        ))}

        {activeView === 'promo' && promoRates.map((rate, idx) => (
          <Card key={idx}>
            <CardContent className="p-4">
              <div className="font-semibold mb-3">{rate.room_type}</div>
              <div className="flex justify-between items-center mb-2">
                <div>
                  <div className="text-sm text-gray-500">Normal Fiyat</div>
                  <div className="text-lg line-through text-gray-400">₺{rate.regular_rate}</div>
                </div>
                <div>
                  <div className="text-sm text-gray-500">Promosyon</div>
                  <div className="text-2xl font-bold text-green-600">₺{rate.promo_rate}</div>
                </div>
              </div>
              <Badge className="bg-green-500 text-white">%{rate.discount_pct} İNDİRİM</Badge>
              <div className="text-xs text-gray-500 mt-2">{rate.conditions}</div>
            </CardContent>
          </Card>
        ))}
      </div>
      <PropertySwitcher onPropertyChange={loadData} />
    </div>
  );
};

export default RateManagementMobile;