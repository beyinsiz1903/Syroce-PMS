import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import Layout from '@/components/Layout';
import axios from 'axios';
import { useTranslation } from 'react-i18next';

const BACKEND = "";

export default function CrossPropertyGuests({ user, tenant, onLogout }) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('search');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const [selectedGuest, setSelectedGuest] = useState(null);
  const [loyaltySummary, setLoyaltySummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const searchGuests = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`/cross-property/guests/search?q=${searchQuery}`, { headers });
      setSearchResults(res.data);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const viewGuestProfile = async (guestId) => {
    try {
      const res = await axios.get(`/cross-property/guests/profile/${guestId}`, { headers });
      setSelectedGuest(res.data);
      setActiveTab('profile');
    } catch (e) { console.error(e); }
  };

  const fetchLoyalty = useCallback(async () => {
    try {
      const res = await axios.get(`/cross-property/guests/loyalty-summary`, { headers });
      setLoyaltySummary(res.data);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { fetchLoyalty(); }, []);

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout}>
      <div className="p-6 space-y-6">
        <div>
          <h1 className="text-2xl font-bold">Cross-Property Misafir Profilleri</h1>
          <p className="text-gray-500">Tek misafir kaydi tum otellerde gecerli</p>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="search">Misafir Ara</TabsTrigger>
            <TabsTrigger value="profile">Birlesik Profil</TabsTrigger>
            <TabsTrigger value="loyalty">Sadakat Ozeti</TabsTrigger>
          </TabsList>

          <TabsContent value="search" className="space-y-4">
            <Card>
              <CardContent className="pt-6">
                <div className="flex gap-2">
                  <Input value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="Ad, e-posta veya telefon ile arama..." onKeyPress={(e) => e.key === 'Enter' && searchGuests()} />
                  <Button onClick={searchGuests} disabled={loading}>{loading ? 'Araniyor...' : 'Ara'}</Button>
                </div>

                {searchResults && (
                  <div className="mt-4 space-y-2">
                    <div className="flex gap-4 text-sm text-gray-500">
                      <span>Toplam: {searchResults.total}</span>
                      <span>Cross-property eslesmeler: {searchResults.cross_property_matches}</span>
                    </div>

                    <div className="border rounded-lg">
                      <table className="w-full">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="text-left p-3 text-sm">Ad</th>
                            <th className="text-left p-3 text-sm">E-posta</th>
                            <th className="text-left p-3 text-sm">Telefon</th>
                            <th className="text-left p-3 text-sm">Otel</th>
                            <th className="text-left p-3 text-sm">Islem</th>
                          </tr>
                        </thead>
                        <tbody>
                          {searchResults.guests?.map((g, i) => (
                            <tr key={i} className="border-t hover:bg-gray-50 cursor-pointer" onClick={() => viewGuestProfile(g.id)}>
                              <td className="p-3 font-medium">{g.name}</td>
                              <td className="p-3 text-sm">{g.email}</td>
                              <td className="p-3 text-sm">{g.phone}</td>
                              <td className="p-3"><Badge variant="outline">{g.tenant_id}</Badge></td>
                              <td className="p-3"><Button size="sm" variant="outline">Profil</Button></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="profile" className="space-y-4">
            {selectedGuest ? (
              <>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Card className="md:col-span-1">
                    <CardHeader><CardTitle>Misafir Bilgileri</CardTitle></CardHeader>
                    <CardContent className="space-y-2">
                      <p className="text-lg font-bold">{selectedGuest.guest?.name}</p>
                      <p className="text-sm text-gray-500">{selectedGuest.guest?.email}</p>
                      <p className="text-sm text-gray-500">{selectedGuest.guest?.phone}</p>
                      <Badge>{selectedGuest.cross_property_records} otelde kayit</Badge>
                    </CardContent>
                  </Card>

                  <Card className="md:col-span-2">
                    <CardHeader><CardTitle>Yasam Boyu Istatistikler</CardTitle></CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="text-center">
                          <div className="text-2xl font-bold text-blue-600">{selectedGuest.lifetime_stats?.total_stays}</div>
                          <p className="text-sm text-gray-500">Toplam Konaklama</p>
                        </div>
                        <div className="text-center">
                          <div className="text-2xl font-bold text-green-600">{selectedGuest.lifetime_stats?.total_nights}</div>
                          <p className="text-sm text-gray-500">Toplam Gece</p>
                        </div>
                        <div className="text-center">
                          <div className="text-2xl font-bold text-purple-600">{selectedGuest.lifetime_stats?.total_spent?.toLocaleString('tr-TR')}</div>
                          <p className="text-sm text-gray-500">Toplam Harcama</p>
                        </div>
                        <div className="text-center">
                          <div className="text-2xl font-bold text-orange-600">{selectedGuest.lifetime_stats?.properties_count}</div>
                          <p className="text-sm text-gray-500">Otel Sayisi</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </div>

                {selectedGuest.stay_history?.length > 0 && (
                  <Card>
                    <CardHeader><CardTitle>Konaklama Geçmişi</CardTitle></CardHeader>
                    <CardContent>
                      <div className="space-y-2">
                        {selectedGuest.stay_history.map((s, i) => (
                          <div key={i} className="flex justify-between p-3 bg-gray-50 rounded">
                            <div>
                              <span className="font-medium">{s.property_name}</span>
                              <span className="text-gray-500 ml-2">Oda: {s.room_number || s.room_type || '-'}</span>
                            </div>
                            <div className="text-sm text-gray-500">
                              {s.check_in ? new Date(s.check_in).toLocaleDateString('tr-TR') : ''} - {s.check_out ? new Date(s.check_out).toLocaleDateString('tr-TR') : ''}
                            </div>
                            <Badge variant="outline">{s.status}</Badge>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}
              </>
            ) : (
              <Card>
                <CardContent className="py-12 text-center text-gray-400">
                  Bir misafir seçin veya arama yapin
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="loyalty" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Cross-Property Sadik Misafirler</CardTitle>
                <CardDescription>Birden fazla otelde konaklama yapan misafirler</CardDescription>
              </CardHeader>
              <CardContent>
                {loyaltySummary?.loyal_guests?.length > 0 ? (
                  <div className="space-y-2">
                    {loyaltySummary.loyal_guests.map((g, i) => (
                      <div key={i} className="flex justify-between items-center p-3 border rounded">
                        <div>
                          <p className="font-medium">{g.name}</p>
                          <p className="text-sm text-gray-500">{g.email}</p>
                        </div>
                        <div className="flex gap-2">
                          <Badge>{g.properties_count} otel</Badge>
                          <Badge variant="outline">{g.total_records} kayit</Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-center py-8 text-gray-400">Cross-property misafir bulunamadı</p>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
}
