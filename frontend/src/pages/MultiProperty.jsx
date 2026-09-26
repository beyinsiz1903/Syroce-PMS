import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Building, Home, MapPin, TrendingUp, Hotel, DollarSign, Loader2, AlertTriangle, RefreshCw, Link2, ReceiptText, UserPlus, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const MultiProperty = ({ embedded = false }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [team, setTeam] = useState(null);
  const [teamError, setTeamError] = useState('');
  const [savingUser, setSavingUser] = useState(false);
  const [userForm, setUserForm] = useState({ property_id: '', name: '', email: '', password: '', role: 'supervisor' });

  const loadTeam = () => {
    axios.get('/platform/multi-property/team')
      .then(({ data: result }) => {
        setTeam(result);
        setUserForm(current => ({
          ...current,
          property_id: current.property_id || result.properties?.[0]?.property_id || '',
        }));
        setTeamError('');
      })
      .catch((requestError) => {
        if (requestError?.response?.status !== 403) setTeamError('Zincir kullanıcıları yüklenemedi.');
      });
  };

  const loadData = () => {
    setLoading(true);
    setError(false);
    axios.get('/multi-property/dashboard')
      .then(res => setData(res.data))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadData(); loadTeam(); }, []);

  const createChainUser = async (event) => {
    event.preventDefault();
    setSavingUser(true);
    setTeamError('');
    try {
      await axios.post('/platform/multi-property/team', userForm);
      setUserForm(current => ({ ...current, name: '', email: '', password: '' }));
      loadTeam();
    } catch (requestError) {
      setTeamError(requestError?.response?.data?.detail || 'Kullanıcı oluşturulamadı.');
    } finally {
      setSavingUser(false);
    }
  };

  return (
    <div className="p-6">
      <div className="mb-8">
        <div className="flex items-center gap-3">
          {!embedded && <Button
            variant="outline"
            size="icon"
            onClick={() => navigate('/app/dashboard')}
            className="hover:bg-blue-50"
            aria-label="Ana sayfa"
          >
            <Home className="w-5 h-5" />
          </Button>}
          <div>
            <h1 className="text-3xl font-bold">Zincir Otel Yönetimi</h1>
            <p className="text-gray-600">Yetkili olduğunuz zincirdeki otellerin konsolide, salt-okunur operasyon görünümü</p>
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
                <div className="grid grid-cols-2 gap-2 mt-4 pt-4 border-t text-xs">
                  <div className="rounded-md bg-slate-50 p-2">
                    <div className="flex items-center gap-1 text-slate-500"><Link2 className="w-3.5 h-3.5" /> Kanal yöneticisi</div>
                    <p className="font-semibold mt-1 capitalize">
                      {property.integrations?.channel_manager?.provider || 'Kurulmadı'} · {property.integrations?.channel_manager?.status || 'not_configured'}
                    </p>
                  </div>
                  <div className="rounded-md bg-slate-50 p-2">
                    <div className="flex items-center gap-1 text-slate-500"><ReceiptText className="w-3.5 h-3.5" /> Nilvera</div>
                    <p className={`font-semibold mt-1 ${property.integrations?.nilvera?.enabled ? 'text-emerald-700' : 'text-slate-600'}`}>
                      {property.integrations?.nilvera?.enabled ? 'Etkin' : 'Kapalı'}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {team && (
        <Card className="mt-6">
          <CardContent className="pt-6">
            <div className="flex items-start justify-between gap-4 mb-5">
              <div>
                <h2 className="text-xl font-bold flex items-center gap-2"><Users className="w-5 h-5 text-blue-600" /> Zincir Kullanıcıları</h2>
                <p className="text-sm text-gray-600 mt-1">Merkez yönetim, kullanıcıyı yalnızca bu zincire bağlı seçilen tesiste yetkilendirir.</p>
              </div>
              <span className="rounded-full bg-blue-50 px-3 py-1 text-sm font-semibold text-blue-700">{team.users?.length || 0} kullanıcı</span>
            </div>

            <form onSubmit={createChainUser} className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-6 gap-3 rounded-lg border bg-slate-50 p-4">
              <select aria-label="Tesis" required value={userForm.property_id} onChange={event => setUserForm({ ...userForm, property_id: event.target.value })} className="h-10 rounded-md border bg-white px-3 text-sm xl:col-span-2">
                {(team.properties || []).map(property => <option key={property.property_id} value={property.property_id}>{property.property_name}</option>)}
              </select>
              <input aria-label="Ad soyad" required minLength={2} placeholder="Ad soyad" value={userForm.name} onChange={event => setUserForm({ ...userForm, name: event.target.value })} className="h-10 rounded-md border bg-white px-3 text-sm" />
              <input aria-label="E-posta" required type="email" placeholder="E-posta" value={userForm.email} onChange={event => setUserForm({ ...userForm, email: event.target.value })} className="h-10 rounded-md border bg-white px-3 text-sm" />
              <input aria-label="Geçici şifre" required minLength={8} type="password" placeholder="Geçici şifre" value={userForm.password} onChange={event => setUserForm({ ...userForm, password: event.target.value })} className="h-10 rounded-md border bg-white px-3 text-sm" />
              <div className="flex gap-2">
                <select aria-label="Rol" value={userForm.role} onChange={event => setUserForm({ ...userForm, role: event.target.value })} className="h-10 min-w-0 flex-1 rounded-md border bg-white px-2 text-sm">
                  <option value="admin">Yönetici</option>
                  <option value="supervisor">Müdür</option>
                  <option value="front_desk">Ön Büro</option>
                  <option value="finance">Muhasebe</option>
                  <option value="housekeeping">Kat Hizmetleri</option>
                </select>
                <Button type="submit" disabled={savingUser} aria-label="Kullanıcı ekle"><UserPlus className="w-4 h-4" /></Button>
              </div>
            </form>

            {teamError && <p className="mt-3 text-sm text-red-600">{teamError}</p>}
            <div className="mt-4 divide-y rounded-lg border">
              {(team.users || []).map(user => (
                <div key={user.id} className="grid grid-cols-1 gap-1 px-4 py-3 text-sm md:grid-cols-3">
                  <span className="font-semibold">{user.name}</span>
                  <span className="text-gray-600">{user.email}</span>
                  <span className="text-gray-600 md:text-right">{user.property_name} · {user.role}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {teamError && !team && <p className="mt-4 text-sm text-red-600">{teamError}</p>}

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
