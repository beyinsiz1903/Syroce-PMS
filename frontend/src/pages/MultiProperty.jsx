import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Building, Home, MapPin, TrendingUp, Hotel, DollarSign, Loader2, AlertTriangle, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const MultiProperty = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const loadData = () => {
    setLoading(true);
    setError(false);
    axios.get('/multi-property/dashboard')
      .then(res => setData(res.data))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadData(); }, []);

  return (
    <div className="p-6">
      <div className="mb-8">
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
            <h1 className="text-3xl font-bold">Multi-Property Dashboard</h1>
            <p className="text-gray-600">Çoklu otel yönetimi ve konsolide raporlar</p>
          </div>
        </div>
      </div>

      {!loading && !error && data && data.summary && (
        <div className="grid grid-cols-4 gap-4 mb-6">
          <Card>
            <CardContent className="pt-6 text-center">
              <Building className="w-10 h-10 text-blue-600 mx-auto mb-2" />
              <p className="text-3xl font-bold">{data.summary.total_properties}</p>
              <p className="text-sm text-gray-500">Oteller</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6 text-center">
              <Hotel className="w-10 h-10 text-indigo-600 mx-auto mb-2" />
              <p className="text-3xl font-bold">{data.summary.total_rooms}</p>
              <p className="text-sm text-gray-500">Toplam Oda</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6 text-center">
              <TrendingUp className="w-10 h-10 text-green-600 mx-auto mb-2" />
              <p className="text-3xl font-bold">{data.summary.avg_occupancy}%</p>
              <p className="text-sm text-gray-500">Ort. Doluluk</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6 text-center">
              <DollarSign className="w-10 h-10 text-amber-600 mx-auto mb-2" />
              <p className="text-3xl font-bold">€{data.summary.total_revenue}</p>
              <p className="text-sm text-gray-500">Bugün Gelir</p>
            </CardContent>
          </Card>
        </div>
      )}

      {!loading && !error && data && data.properties && data.properties.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {data.properties.map((property) => (
            <Card key={property.property_id} className="hover:shadow-lg transition-shadow cursor-pointer">
              <CardContent className="pt-6">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h3 className="text-xl font-bold mb-2">{property.property_name}</h3>
                    <div className="flex items-center gap-2 text-gray-600">
                      <MapPin className="w-4 h-4" />
                      <span className="text-sm">{property.location || 'Istanbul'}</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-3xl font-bold text-indigo-600">{property.occupancy_pct}%</p>
                    <p className="text-xs text-gray-500">Doluluk</p>
                  </div>
                </div>
                
                <div className="grid grid-cols-3 gap-4 mt-4 pt-4 border-t">
                  <div>
                    <p className="text-xs text-gray-500">{t("pms.rooms")}</p>
                    <p className="text-lg font-bold">{property.total_rooms}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">ADR</p>
                    <p className="text-lg font-bold">€{property.adr}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">{t("finance.revenue")}</p>
                    <p className="text-lg font-bold">€{property.today_revenue}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {loading && (
        <Card>
          <CardContent className="pt-8 text-center">
            <Loader2 className="w-8 h-8 text-blue-600 mx-auto mb-3 animate-spin" />
            <p className="text-gray-600">Yükleniyor...</p>
          </CardContent>
        </Card>
      )}

      {!loading && error && (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="pt-8 text-center">
            <AlertTriangle className="w-12 h-12 text-red-500 mx-auto mb-3" />
            <p className="text-red-700 mb-4">Multi-property verileri yüklenemedi.</p>
            <Button variant="outline" onClick={loadData}>
              <RefreshCw className="w-4 h-4 mr-2" />
              Tekrar Dene
            </Button>
          </CardContent>
        </Card>
      )}

      {!loading && !error && (!data || !data.properties || data.properties.length === 0) && (
        <Card>
          <CardContent className="pt-8 text-center">
            <Building className="w-16 h-16 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-600">Gösterilecek otel bulunamadı.</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default MultiProperty;