import { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { FlaskConical, Loader2, XCircle, AlertTriangle, Search, ArrowRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
const STEPS = [{
  id: 1,
  title: 'Test Rezervasyon Oluşturun',
  description: 'Exely\'nin bağlı olduğu OTA platformunda (Booking.com vb.) test bir rezervasyon oluşturun.'
}, {
  id: 2,
  title: 'Bilgileri Girin',
  description: 'Rezervasyon ID veya misafir adını girerek arama yapabilirsiniz. Boş bırakırsanız tüm yeni rezervasyonlar çekilir.'
}, {
  id: 3,
  title: 'Doğrulama Başlatın',
  description: 'OTA_ReadRQ ile Exely üzerinden rezervasyon çekilecek ve PMS\'e aktarımı kontrol edilecek.'
}];
const TestBookingVerification = () => {
  const {
    t
  } = useTranslation();
  const [step, setStep] = useState(1);
  const [reservationId, setReservationId] = useState('');
  const [guestName, setGuestName] = useState('');
  const [expectedAdults, setExpectedAdults] = useState('');
  const [expectedChildAges, setExpectedChildAges] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const headers = {};
  const handleVerify = async () => {
    setLoading(true);
    setResult(null);
    try {
      const payload = {};
      if (reservationId.trim()) payload.reservation_id = reservationId.trim();
      if (guestName.trim()) payload.guest_name = guestName.trim();
      if (expectedAdults !== '' || expectedChildAges.trim()) {
        const ages = expectedChildAges.trim() ? expectedChildAges.split(',').map(age => age.trim()) : [];
        if (!reservationId.trim() || !/^\d+$/.test(expectedAdults) || ages.some(age => !/^\d+$/.test(age) || Number(age) > 17)) {
          toast.error('Karşılaştırma için rezervasyon ID, yetişkin sayısı ve 0–17 arasında tam çocuk yaşları girin.');
          return;
        }
        payload.expected_adults = Number(expectedAdults);
        payload.expected_children_ages = ages.map(Number);
      }
      const res = await axios.post(`/channel-manager/exely/test-booking/verify`, payload, {
        headers
      });
      setResult(res.data);
      setStep(3);
      if (res.data.verification_status === 'found') {
        toast.info(res.data.acceptance_status === 'mismatch' ? 'Rezervasyon bulundu; beklenen kişi bilgileri eşleşmiyor.' : 'Rezervasyon bulundu; tam kabul doğrulaması tamamlanmadı.');
      } else if (res.data.verification_status === 'error') {
        toast.error('Doğrulama sırasında hata oluştu');
      } else {
        toast.info('Yeni rezervasyon bulunamadı. Lütfen birkaç dakika bekleyip tekrar deneyin.');
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Doğrulama başarısız');
    } finally {
      setLoading(false);
    }
  };
  return <Card data-testid="test-booking-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FlaskConical className="w-5 h-5 text-indigo-600" />
          {t('cm.components_TestBookingVerification.test_booking_dogrulama')}
        </CardTitle>
        <CardDescription>
          {t('cm.components_TestBookingVerification.ota_platformundan_olusturulan_test_rezer')}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Step Indicator */}
        <div className="flex items-center gap-2">
          {STEPS.map((s, i) => <div key={s.id} className="flex items-center gap-2">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${step >= s.id ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-500'}`} data-testid={`step-indicator-${s.id}`}>
                {s.id}
              </div>
              {i < STEPS.length - 1 && <ArrowRight className="w-4 h-4 text-gray-300" />}
            </div>)}
        </div>

        {/* Step Content */}
        <div className="bg-gray-50 rounded-lg p-4">
          <h4 className="font-medium text-sm">{STEPS[step - 1].title}</h4>
          <p className="text-sm text-gray-500 mt-1">{STEPS[step - 1].description}</p>
        </div>

        {step >= 1 && <div className="space-y-3">
            <div>
              <Label>{t('cm.components_TestBookingVerification.rezervasyon_id_opsiyonel')}</Label>
              <Input placeholder="Exely reservation ID girin..." value={reservationId} onChange={e => setReservationId(e.target.value)} className="mt-1" data-testid="test-booking-reservation-id" />
            </div>
            <div>
              <Label>{t('cm.components_TestBookingVerification.misafir_adi_opsiyonel')}</Label>
              <Input placeholder={t('cm.components_TestBookingVerification.misafir_adini_girin')} value={guestName} onChange={e => setGuestName(e.target.value)} className="mt-1" data-testid="test-booking-guest-name" />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <Label htmlFor="exely-expected-adults">Beklenen yetişkin sayısı (isteğe bağlı)</Label>
                <Input id="exely-expected-adults" type="number" min="0" max="1000" step="1" value={expectedAdults} onChange={e => setExpectedAdults(e.target.value)} />
              </div>
              <div>
                <Label htmlFor="exely-expected-child-ages">Beklenen çocuk yaşları</Label>
                <Input id="exely-expected-child-ages" placeholder="Örn. 6, 12 — çocuk yoksa boş" value={expectedChildAges} onChange={e => setExpectedChildAges(e.target.value)} />
              </div>
            </div>
            <p className="text-xs text-slate-500">Giriş tarihindeki tamamlanmış yaşları yazın. Beklenen değerler yalnız karşılaştırılır; mevcut kişi ve tutar bilgilerini düzeltmez. Yeni teslim edilmemiş kayıtlar standart akışla aktarılabilir.</p>
            <div className="flex gap-2">
              <Button onClick={() => {
            setStep(2);
            handleVerify();
          }} disabled={loading} className="bg-indigo-600 hover:bg-indigo-700" data-testid="test-booking-verify-btn">
                {loading ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> {t('cm.components_TestBookingVerification.dogrulaniyor')}</> : <><Search className="w-4 h-4 mr-1" /> {t('cm.components_TestBookingVerification.ota_readrq_ile_dogrula')}</>}
              </Button>
              {result && <Button variant="outline" onClick={() => {
            setResult(null);
            setStep(1);
          }} data-testid="test-booking-reset-btn">
                  {t('cm.components_TestBookingVerification.sifirla')}
                </Button>}
            </div>
          </div>}

        {/* Results */}
        {result && <div className="space-y-4 mt-4" data-testid="test-booking-results">
            {/* Status Banner */}
            <div className={`rounded-lg p-4 flex items-start gap-3 ${result.verification_status === 'error' || result.acceptance_status === 'mismatch' ? 'bg-red-50 border border-red-200' : 'bg-yellow-50 border border-yellow-200'}`}>
              {result.verification_status === 'error' ? <XCircle className="w-5 h-5 text-red-600 mt-0.5" /> : <AlertTriangle className="w-5 h-5 text-yellow-600 mt-0.5" />}
              <div>
                <p className="font-medium text-sm">
                  {result.verification_status === 'found' ? result.acceptance_status === 'mismatch' ? 'Kişi bilgileri eşleşmiyor' : 'Rezervasyon bulundu — tam kabul bekliyor' : result.verification_status === 'error' ? 'Doğrulama Hatası' : 'Rezervasyon Bulunamadı'}
                </p>
                <p className="text-xs text-gray-600 mt-1">
                  {t('cm.components_TestBookingVerification.onceki')} {result.before_count} | Sonraki: {result.after_count} {t('cm.components_TestBookingVerification.yeni')} {result.new_count}
                </p>
              </div>
            </div>
            {result.lookup_source === 'stored' && <p className="text-xs text-slate-600">Mevcut PMS kaydı gösteriliyor. Exely’den yeni yanıt alındığı anlamına gelmez; onaylanmış kayıtlar Undelivered listesinde bulunmayabilir.</p>}
            {(result.warnings || []).map((warning, index) => <p key={index} className="text-xs text-amber-800">{warning}</p>)}

            {/* New Reservations */}
            {result.new_reservations?.length > 0 && <div>
                <h4 className="text-sm font-medium mb-2">Bulunan Rezervasyonlar</h4>
                <div className="space-y-2">
                  {result.new_reservations.map((r, i) => <div key={r.id || i} className="bg-white border rounded p-3 flex items-center justify-between" data-testid={`found-reservation-${i}`}>
                      <div>
                        <span className="font-medium text-sm">{r.guest_name || 'Bilinmeyen'}</span>
                        <code className="ml-2 text-xs bg-gray-100 px-1 rounded">{r.external_id}</code>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge className="text-xs" variant="outline">{r.state || r.status || r.ingest_action || 'unknown'}</Badge>
                        {r.checks?.guest_demographics === 'not_verified' && <Badge variant="outline">Kişi ayrımı doğrulanmadı</Badge>}
                      </div>
                    </div>)}
                </div>
              </div>}

            {/* Errors */}
            {result.errors?.length > 0 && <div>
                <h4 className="text-sm font-medium text-red-600 mb-2">Hatalar</h4>
                {result.errors.map((err, i) => <div key={err.id || i} className="bg-red-50 rounded p-2 text-xs text-red-700 mb-1">{err}</div>)}
              </div>}

            {/* Pull result details */}
            {result.pull_result && <div className="text-xs text-gray-500 bg-gray-50 rounded p-2">
                Pull: {result.pull_result.success ? 'Başarılı' : 'Başarısız'} {t('cm.components_TestBookingVerification.islenen')} {result.pull_result.processed || 0}
                {result.pull_result.error && ` | Hata: ${result.pull_result.error}`}
              </div>}
          </div>}
      </CardContent>
    </Card>;
};
export default TestBookingVerification;
