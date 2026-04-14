import { useState, useMemo } from 'react';
import { TabsContent } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Plus, User, Search, Star, Phone, Mail, CreditCard, MapPin, Merge, Settings, UserCheck } from 'lucide-react';

const GuestsTab = ({ guests, setOpenDialog, setSelectedGuest360, loadGuest360, setNewBooking, t }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchField, setSearchField] = useState('all');
  const [showMergeDialog, setShowMergeDialog] = useState(false);
  const [mergeGuest1, setMergeGuest1] = useState('');
  const [mergeGuest2, setMergeGuest2] = useState('');
  const [showPreferencesDialog, setShowPreferencesDialog] = useState(false);
  const [selectedGuestForPref, setSelectedGuestForPref] = useState(null);
  const [preferences, setPreferences] = useState({
    pillow_type: '', room_temperature: '', floor_preference: '',
    newspaper: '', minibar_preference: '', smoking: false,
    extra_towels: false, late_checkout_preferred: false, notes: ''
  });

  const filteredGuests = useMemo(() => {
    if (!searchQuery) return guests;
    const q = searchQuery.toLowerCase();
    return guests.filter(g => {
      if (searchField === 'name' || searchField === 'all') {
        if ((g.name || '').toLowerCase().includes(q)) return true;
      }
      if (searchField === 'phone' || searchField === 'all') {
        if ((g.phone || '').includes(q)) return true;
      }
      if (searchField === 'email' || searchField === 'all') {
        if ((g.email || '').toLowerCase().includes(q)) return true;
      }
      if (searchField === 'id' || searchField === 'all') {
        if ((g.id_number || g.passport_number || '').includes(q)) return true;
      }
      return false;
    });
  }, [guests, searchQuery, searchField]);

  return (
    <TabsContent value="guests" className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold" data-testid="guests-tab-title">Misafirler ({guests.length})</h2>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowMergeDialog(true)}>
            <Merge className="w-4 h-4 mr-2" /> Misafir Birlestir
          </Button>
          <Button onClick={() => setOpenDialog('guest')} data-testid="add-guest-btn">
            <Plus className="w-4 h-4 mr-2" /> Yeni Misafir
          </Button>
        </div>
      </div>

      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400" />
          <Input className="pl-9" placeholder="Isim, telefon, e-posta veya kimlik no ile ara..."
            value={searchQuery} onChange={e => setSearchQuery(e.target.value)} />
        </div>
        <div className="flex border rounded-md overflow-hidden">
          {[
            { key: 'all', label: 'Tumu' },
            { key: 'name', label: 'Isim' },
            { key: 'phone', label: 'Telefon' },
            { key: 'email', label: 'E-posta' },
            { key: 'id', label: 'Kimlik' },
          ].map(f => (
            <button key={f.key} onClick={() => setSearchField(f.key)}
              className={`px-3 py-1.5 text-xs transition ${searchField === f.key ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {filteredGuests.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="py-8 text-center text-gray-400">
            <User className="w-10 h-10 mx-auto mb-2 opacity-30" />
            <p>{searchQuery ? 'Aramanizla eslesen misafir bulunamadi' : 'Henuz misafir kaydedilmemis'}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredGuests.map((guest) => (
            <Card key={guest.id} data-testid={`guest-card-${guest.id}`} className="hover:shadow-md transition">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 bg-teal-600 text-white rounded-full flex items-center justify-center text-sm font-bold">
                      {(guest.name || 'M')[0]?.toUpperCase()}
                    </div>
                    <div>
                      <CardTitle className="text-base flex items-center gap-1">
                        {guest.name}
                        {guest.vip_status && <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-500" />}
                      </CardTitle>
                      {guest.total_stays > 1 && (
                        <Badge variant="outline" className="text-[9px] h-4 mt-0.5">
                          <UserCheck className="w-2.5 h-2.5 mr-0.5" /> {guest.total_stays}. konaklama
                        </Badge>
                      )}
                    </div>
                  </div>
                  <Button size="sm" variant="outline"
                    onClick={() => { setSelectedGuest360(guest.id); loadGuest360(guest.id); }}
                    data-testid={`guest-profile-btn-${guest.id}`}>
                    <User className="w-4 h-4 mr-1" /> Profil
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="space-y-1.5">
                  {guest.email && (
                    <div className="flex items-center gap-2 text-gray-600">
                      <Mail className="w-3.5 h-3.5 text-gray-400" /> <span className="text-xs">{guest.email}</span>
                    </div>
                  )}
                  {guest.phone && (
                    <div className="flex items-center gap-2 text-gray-600">
                      <Phone className="w-3.5 h-3.5 text-gray-400" /> <span className="text-xs">{guest.phone}</span>
                    </div>
                  )}
                  {(guest.id_number || guest.passport_number) && (
                    <div className="flex items-center gap-2 text-gray-600">
                      <CreditCard className="w-3.5 h-3.5 text-gray-400" /> <span className="text-xs">{guest.id_number || guest.passport_number}</span>
                    </div>
                  )}
                  {guest.address && (
                    <div className="flex items-center gap-2 text-gray-600">
                      <MapPin className="w-3.5 h-3.5 text-gray-400" /> <span className="text-xs truncate">{guest.address}</span>
                    </div>
                  )}
                </div>
                <div className="flex gap-2 pt-2 border-t">
                  <Button size="sm" variant="outline" className="flex-1 h-7 text-xs"
                    onClick={() => { setNewBooking(prev => ({ ...prev, guest_id: guest.id })); setOpenDialog('newbooking'); }}
                    data-testid={`guest-new-booking-btn-${guest.id}`}>
                    <Plus className="w-3 h-3 mr-1" /> Rezervasyon
                  </Button>
                  <Button size="sm" variant="outline" className="h-7 text-xs"
                    onClick={() => { setSelectedGuestForPref(guest); setPreferences(guest.preferences || {}); setShowPreferencesDialog(true); }}>
                    <Settings className="w-3 h-3 mr-1" /> Tercihler
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={showMergeDialog} onOpenChange={setShowMergeDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Merge className="w-5 h-5" /> Misafir Birlestir</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <p className="text-sm text-gray-500">Ayni misafirin farkli kayitlarini birlestirin. Tum konaklama gecmisi ve notlar ana kayda aktarilir.</p>
            <div>
              <Label>Ana Kayit (Korunacak)</Label>
              <select className="w-full border rounded-md p-2 text-sm" value={mergeGuest1} onChange={e => setMergeGuest1(e.target.value)}>
                <option value="">Misafir seciniz...</option>
                {guests.map(g => <option key={g.id} value={g.id}>{g.name} - {g.email || g.phone || 'Bilgi yok'}</option>)}
              </select>
            </div>
            <div>
              <Label>Birlestirilecek Kayit (Silinecek)</Label>
              <select className="w-full border rounded-md p-2 text-sm" value={mergeGuest2} onChange={e => setMergeGuest2(e.target.value)}>
                <option value="">Misafir seciniz...</option>
                {guests.filter(g => g.id !== mergeGuest1).map(g => <option key={g.id} value={g.id}>{g.name} - {g.email || g.phone || 'Bilgi yok'}</option>)}
              </select>
            </div>
            <Button className="w-full" disabled={!mergeGuest1 || !mergeGuest2}
              onClick={() => { setShowMergeDialog(false); }}>
              <Merge className="w-4 h-4 mr-2" /> Birlestir
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showPreferencesDialog} onOpenChange={setShowPreferencesDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Settings className="w-5 h-5" /> Misafir Tercihleri - {selectedGuestForPref?.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Yastik Tercihi</Label>
                <select className="w-full border rounded-md p-2 text-sm" value={preferences.pillow_type || ''} onChange={e => setPreferences(p => ({ ...p, pillow_type: e.target.value }))}>
                  <option value="">Belirtilmemis</option>
                  <option value="soft">Yumusak</option>
                  <option value="firm">Sert</option>
                  <option value="memory">Visco</option>
                  <option value="feather">Kaz Tuyu</option>
                </select>
              </div>
              <div>
                <Label>Oda Sicakligi</Label>
                <select className="w-full border rounded-md p-2 text-sm" value={preferences.room_temperature || ''} onChange={e => setPreferences(p => ({ ...p, room_temperature: e.target.value }))}>
                  <option value="">Belirtilmemis</option>
                  <option value="cold">Serin (18-20°C)</option>
                  <option value="normal">Normal (21-23°C)</option>
                  <option value="warm">Ilik (24-26°C)</option>
                </select>
              </div>
              <div>
                <Label>Kat Tercihi</Label>
                <select className="w-full border rounded-md p-2 text-sm" value={preferences.floor_preference || ''} onChange={e => setPreferences(p => ({ ...p, floor_preference: e.target.value }))}>
                  <option value="">Belirtilmemis</option>
                  <option value="low">Alt Katlar</option>
                  <option value="high">Ust Katlar</option>
                  <option value="any">Farketmez</option>
                </select>
              </div>
              <div>
                <Label>Gazete</Label>
                <select className="w-full border rounded-md p-2 text-sm" value={preferences.newspaper || ''} onChange={e => setPreferences(p => ({ ...p, newspaper: e.target.value }))}>
                  <option value="">Istenmiyor</option>
                  <option value="hurriyet">Hurriyet</option>
                  <option value="sabah">Sabah</option>
                  <option value="milliyet">Milliyet</option>
                  <option value="financial_times">Financial Times</option>
                </select>
              </div>
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <input type="checkbox" checked={preferences.extra_towels || false} onChange={e => setPreferences(p => ({ ...p, extra_towels: e.target.checked }))} />
                <span className="text-sm">Ekstra havlu</span>
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" checked={preferences.late_checkout_preferred || false} onChange={e => setPreferences(p => ({ ...p, late_checkout_preferred: e.target.checked }))} />
                <span className="text-sm">Gec cikis tercihi</span>
              </div>
            </div>
            <div>
              <Label>Ozel Notlar</Label>
              <Textarea value={preferences.notes || ''} onChange={e => setPreferences(p => ({ ...p, notes: e.target.value }))} placeholder="Alerji, diyet, ozel istekler..." rows={2} />
            </div>
            <Button className="w-full" onClick={() => { setShowPreferencesDialog(false); }}>
              Tercihleri Kaydet
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </TabsContent>
  );
};

export default GuestsTab;
