import { useState, useEffect } from 'react';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { CheckCircle, XCircle, AlertTriangle, Loader2, FileText, Shield, Send, Search, Fingerprint } from 'lucide-react';

export default function TcKimlikPage() {
  const [tab, setTab] = useState('validate');
  
  // TC Validation state
  const [tcNo, setTcNo] = useState('');
  const [validationResult, setValidationResult] = useState(null);
  const [validating, setValidating] = useState(false);
  
  // Emniyet bildirimi state
  const [bildirimiList, setBildirimiList] = useState([]);
  const [loadingBildirimi, setLoadingBildirimi] = useState(false);
  const [selectedForm, setSelectedForm] = useState(null);
  
  // Guest search for emniyet bildirimi
  const [guestSearch, setGuestSearch] = useState('');
  const [guests, setGuests] = useState([]);
  const [searchingGuests, setSearchingGuests] = useState(false);
  const [creatingBildirimi, setCreatingBildirimi] = useState(null);

  useEffect(() => {
    if (tab === 'emniyet') loadBildirimleri();
  }, [tab]);

  const validateTc = async () => {
    if (!tcNo.trim()) return;
    setValidating(true);
    try {
      const result = await api.validateTcKimlik(tcNo);
      setValidationResult(result);
    } catch (err) {
      setValidationResult({ is_valid: false, errors: [err.message] });
    } finally {
      setValidating(false);
    }
  };

  const loadBildirimleri = async () => {
    setLoadingBildirimi(true);
    try {
      const res = await api.getEmniyetBildirimleri();
      setBildirimiList(res.forms || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingBildirimi(false);
    }
  };

  const searchGuests = async () => {
    if (!guestSearch.trim()) return;
    setSearchingGuests(true);
    try {
      const res = await api.getGuests({ search: guestSearch, limit: 10 });
      setGuests(res.guests || []);
    } catch (err) {
      console.error(err);
    } finally {
      setSearchingGuests(false);
    }
  };

  const createBildirimi = async (guestId) => {
    setCreatingBildirimi(guestId);
    try {
      const res = await api.createEmniyetBildirimi(guestId);
      if (res.success) {
        setSelectedForm(res.form);
        loadBildirimleri();
      }
    } catch (err) {
      alert(err.message);
    } finally {
      setCreatingBildirimi(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">TC Kimlik & Emniyet</h1>
        <p className="text-gray-500 mt-1">TC Kimlik No doğrulama ve Emniyet Müdürlüğü bildirimleri</p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="grid grid-cols-2 w-full max-w-md">
          <TabsTrigger value="validate"><Fingerprint className="w-4 h-4 mr-2" />TC Doğrulama</TabsTrigger>
          <TabsTrigger value="emniyet"><Shield className="w-4 h-4 mr-2" />Emniyet Bildirimi</TabsTrigger>
        </TabsList>

        {/* TC Validation Tab */}
        <TabsContent value="validate" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Fingerprint className="w-5 h-5 text-blue-500" />
                TC Kimlik No Doğrulama
              </CardTitle>
              <CardDescription>TC Kimlik No'nun geçerliliğini matematiksel algoritma ile kontrol eder (11 haneli)</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-3">
                <Input 
                  placeholder="TC Kimlik No (11 hane)" 
                  value={tcNo} 
                  onChange={(e) => { setTcNo(e.target.value.replace(/\D/g, '').slice(0, 11)); setValidationResult(null); }}
                  maxLength={11}
                  className="font-mono text-lg tracking-wider"
                />
                <Button onClick={validateTc} disabled={validating || tcNo.length !== 11}>
                  {validating ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Doğrula'}
                </Button>
              </div>

              {tcNo.length > 0 && tcNo.length < 11 && (
                <p className="text-sm text-gray-500">{11 - tcNo.length} hane daha gerekli</p>
              )}

              {validationResult && (
                <div className={`rounded-lg p-4 ${validationResult.is_valid ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
                  <div className="flex items-center gap-3 mb-3">
                    {validationResult.is_valid ? (
                      <CheckCircle className="w-8 h-8 text-green-500" />
                    ) : (
                      <XCircle className="w-8 h-8 text-red-500" />
                    )}
                    <div>
                      <p className="font-bold text-lg">{validationResult.is_valid ? 'Geçerli TC Kimlik No' : 'Geçersiz TC Kimlik No'}</p>
                      <p className="text-sm font-mono">{validationResult.tc_no}</p>
                    </div>
                  </div>

                  {validationResult.errors && validationResult.errors.length > 0 && (
                    <div className="text-sm text-red-600 space-y-1">
                      {validationResult.errors.map((e, i) => <p key={i}>❌ {e}</p>)}
                    </div>
                  )}

                  {validationResult.checks && (
                    <div className="mt-3 space-y-1">
                      <p className="text-sm font-medium mb-1">Kontrol Adımları:</p>
                      {Object.entries(validationResult.checks).map(([key, val]) => (
                        <div key={key} className="flex items-center gap-2 text-sm">
                          {val ? <CheckCircle className="w-4 h-4 text-green-500" /> : <XCircle className="w-4 h-4 text-red-400" />}
                          <span className={val ? 'text-green-700' : 'text-red-600'}>
                            {key === 'length' ? '11 hane kontrolü' :
                             key === 'numeric' ? 'Sayısal kontrol' :
                             key === 'first_digit' ? 'İlk hane kontrolü' :
                             key === 'check_digit_10' ? '10. hane doğrulama' :
                             key === 'check_digit_11' ? '11. hane doğrulama' : key}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Emniyet Bildirimi Tab */}
        <TabsContent value="emniyet" className="space-y-4">
          {/* Search guest for new bildirimi */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Send className="w-5 h-5 text-blue-500" />
                Yeni Emniyet Bildirimi
              </CardTitle>
              <CardDescription>Yabancı uyruklu misafir için Emniyet Müdürlüğü bildirim formu oluşturun</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-3">
                <Input 
                  placeholder="Misafir ara (ad, soyad, kimlik no)" 
                  value={guestSearch} 
                  onChange={(e) => setGuestSearch(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && searchGuests()}
                />
                <Button variant="outline" onClick={searchGuests} disabled={searchingGuests}>
                  {searchingGuests ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                </Button>
              </div>

              {guests.length > 0 && (
                <div className="border rounded-lg divide-y">
                  {guests.map((guest) => (
                    <div key={guest.id} className="p-3 flex items-center justify-between hover:bg-gray-50">
                      <div>
                        <p className="font-medium">{guest.first_name} {guest.last_name}</p>
                        <div className="flex gap-2 text-xs text-gray-500">
                          <span>{guest.nationality || 'Uyruk belirtilmemiş'}</span>
                          <span>•</span>
                          <span>{guest.id_number || '-'}</span>
                        </div>
                      </div>
                      <Button size="sm" onClick={() => createBildirimi(guest.id)} disabled={creatingBildirimi === guest.id}>
                        {creatingBildirimi === guest.id ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <FileText className="w-3 h-3 mr-1" />}
                        Bildirim Oluştur
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Existing forms */}
          <Card>
            <CardHeader>
              <CardTitle>Bildirim Geçmişi</CardTitle>
              <CardDescription>Oluşturulmuş Emniyet bildirimleri</CardDescription>
            </CardHeader>
            <CardContent>
              {loadingBildirimi ? (
                <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
              ) : bildirimiList.length === 0 ? (
                <p className="text-center text-gray-500 py-8">Henüz bildirim yok</p>
              ) : (
                <div className="space-y-2">
                  {bildirimiList.map((form) => (
                    <div key={form.form_id || form.id} className="p-3 border rounded-lg flex items-center justify-between hover:bg-gray-50 cursor-pointer"
                         onClick={() => setSelectedForm(form)}>
                      <div>
                        <p className="font-medium">{form.misafir_bilgileri?.ad} {form.misafir_bilgileri?.soyad}</p>
                        <div className="flex gap-2 text-xs text-gray-500">
                          <span>{form.misafir_bilgileri?.uyruk}</span>
                          <span>•</span>
                          <span>{new Date(form.created_at).toLocaleDateString('tr-TR')}</span>
                        </div>
                      </div>
                      <Badge variant={form.status === 'submitted' ? 'default' : 'outline'}>
                        {form.status === 'submitted' ? 'Gönderildi' : form.status === 'draft' ? 'Taslak' : form.status}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Form Detail Dialog */}
      <Dialog open={!!selectedForm} onOpenChange={() => setSelectedForm(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Emniyet Bildirimi Formu</DialogTitle>
            <DialogDescription>{selectedForm?.form_title}</DialogDescription>
          </DialogHeader>
          {selectedForm && (
            <div className="space-y-4">
              <div className="bg-blue-50 rounded-lg p-3 text-sm">
                <p className="font-medium text-blue-800">Yasal Dayanak: {selectedForm.yasal_dayanak}</p>
                <p className="text-blue-600">Bildirim Süresi: {selectedForm.bildirim_suresi}</p>
              </div>

              {/* Tesis Bilgileri */}
              <div>
                <h4 className="font-semibold text-sm mb-2">Tesis Bilgileri</h4>
                <div className="grid grid-cols-2 gap-2 text-sm bg-gray-50 rounded-lg p-3">
                  {selectedForm.tesis_bilgileri && Object.entries(selectedForm.tesis_bilgileri).map(([k, v]) => (
                    <div key={k}>
                      <span className="text-gray-500 capitalize">{k.replace(/_/g, ' ')}:</span>
                      <span className="ml-1 font-medium">{v || '-'}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Misafir Bilgileri */}
              <div>
                <h4 className="font-semibold text-sm mb-2">Misafir Bilgileri</h4>
                <div className="grid grid-cols-2 gap-2 text-sm bg-gray-50 rounded-lg p-3">
                  {selectedForm.misafir_bilgileri && Object.entries(selectedForm.misafir_bilgileri).map(([k, v]) => (
                    <div key={k}>
                      <span className="text-gray-500 capitalize">{k.replace(/_/g, ' ')}:</span>
                      <span className="ml-1 font-medium">{v || '-'}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Belge Bilgileri */}
              <div>
                <h4 className="font-semibold text-sm mb-2">Belge Bilgileri</h4>
                <div className="grid grid-cols-2 gap-2 text-sm bg-gray-50 rounded-lg p-3">
                  {selectedForm.belge_bilgileri && Object.entries(selectedForm.belge_bilgileri).map(([k, v]) => (
                    <div key={k}>
                      <span className="text-gray-500 capitalize">{k.replace(/_/g, ' ')}:</span>
                      <span className="ml-1 font-medium">{v || '-'}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-700">
                <AlertTriangle className="w-4 h-4 inline mr-1" />
                {selectedForm.notes}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
