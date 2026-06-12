import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Star, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const apiBase = (import.meta.env.VITE_BACKEND_URL || '').replace(/\/$/, '');
const publicAxios = axios.create({ baseURL: apiBase ? `${apiBase}/api` : '/api' });

const PublicReviewPage = () => {
  const { t } = useTranslation();
  const { token } = useParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [invite, setInvite] = useState(null);

  const [rating, setRating] = useState(0);
  const [hover, setHover] = useState(0);
  const [comment, setComment] = useState('');
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      try {
        const res = await publicAxios.get(`/feedback/public/invite/${encodeURIComponent(token)}`);
        if (!active) return;
        setInvite(res.data);
        setName(res.data?.guest_name || '');
      } catch (err) {
        if (!active) return;
        setError(err?.response?.data?.detail || 'Bağlantı doğrulanamadı');
      }
      if (active) setLoading(false);
    })();
    return () => { active = false; };
  }, [token]);

  const submit = async () => {
    if (!rating) return;
    setSubmitting(true);
    try {
      await publicAxios.post(`/feedback/public/invite/${encodeURIComponent(token)}`, {
        rating,
        comment: comment.trim(),
        guest_name: name.trim(),
      });
      setDone(true);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Değerlendirme gönderilemedi');
    }
    setSubmitting(false);
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-slate-100 dark:bg-none dark:bg-background p-4">
        <div className="flex flex-col items-center gap-3 text-gray-600">
          <Loader2 className="w-8 h-8 animate-spin" />
          <p>{t('cm.pages_PublicReviewPage.yukleniyor')}</p>
        </div>
      </div>
    );
  }

  if (error && !invite) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-slate-100 dark:bg-none dark:bg-background p-4">
        <Card className="w-full max-w-md">
          <CardContent className="p-8 text-center">
            <AlertCircle className="w-14 h-14 mx-auto mb-3 text-red-400" />
            <h2 className="text-lg font-semibold mb-2">{t('cm.pages_PublicReviewPage.baglanti_gecersiz')}</h2>
            <p className="text-sm text-gray-600">{error}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (done) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-slate-100 dark:bg-none dark:bg-background p-4">
        <Card className="w-full max-w-md">
          <CardContent className="p-8 text-center">
            <CheckCircle2 className="w-16 h-16 mx-auto mb-4 text-green-500" />
            <h2 className="text-xl font-semibold mb-2">{t('cm.pages_PublicReviewPage.tesekkur_ederiz')}</h2>
            <p className="text-sm text-gray-600">
              {t('cm.pages_PublicReviewPage.degerlendirmeniz')} {invite?.hotel_name || 'otele'} {t('cm.pages_PublicReviewPage.iletildi_geri_bildiriminiz_hizmet_kalite')}
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-slate-100 dark:bg-none dark:bg-background p-4 py-12">
      <div className="max-w-xl mx-auto">
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="text-xl">{invite?.hotel_name || 'Otel'}</CardTitle>
            <p className="text-sm text-gray-500">{t('cm.pages_PublicReviewPage.konaklama_degerlendirmesi')}</p>
          </CardHeader>
          <CardContent className="p-6 space-y-6">
            <div className="text-sm text-gray-700 bg-blue-50 border border-blue-100 rounded-lg p-3">
              {invite?.guest_name && <p>{t('cm.pages_PublicReviewPage.sayin')} <strong>{invite.guest_name}</strong>{t('cm.pages_PublicReviewPage.konaklamanizi_degerlendirir_misiniz')}</p>}
              {!invite?.guest_name && <p>{t('cm.pages_PublicReviewPage.konaklamanizi_degerlendirir_misiniz_339b4')}</p>}
              {(invite?.check_in || invite?.check_out) && (
                <p className="text-xs text-gray-500 mt-1">
                  {invite.check_in} → {invite.check_out}
                  {invite.room_number ? ` · Oda ${invite.room_number}` : ''}
                </p>
              )}
            </div>

            <div>
              <Label className="block mb-2 font-medium">{t('cm.pages_PublicReviewPage.genel_puaniniz')}</Label>
              <div
                className="flex gap-2 justify-center"
                onMouseLeave={() => setHover(0)}
              >
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setRating(n)}
                    onMouseEnter={() => setHover(n)}
                    aria-label={`${n} yıldız`}
                    className="p-1 rounded-md hover:bg-yellow-50 focus:outline-none focus:ring-2 focus:ring-yellow-400"
                  >
                    <Star
                      className={`w-10 h-10 transition ${
                        n <= (hover || rating)
                          ? 'text-yellow-400 fill-yellow-400'
                          : 'text-gray-300'
                      }`}
                    />
                  </button>
                ))}
              </div>
              {rating > 0 && (
                <p className="text-center text-xs text-gray-500 mt-2">
                  {['Çok kötü', 'Kötü', 'Orta', 'İyi', 'Mükemmel'][rating - 1]}
                </p>
              )}
            </div>

            <div>
              <Label htmlFor="review-name" className="block mb-2">{t('cm.pages_PublicReviewPage.adiniz_istege_bagli')}</Label>
              <Input
                id="review-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={120}
                placeholder={t('cm.pages_PublicReviewPage.adiniz')}
              />
            </div>

            <div>
              <Label htmlFor="review-comment" className="block mb-2">{t('cm.pages_PublicReviewPage.yorumunuz_istege_bagli')}</Label>
              <Textarea
                id="review-comment"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                rows={5}
                maxLength={2000}
                placeholder={t('cm.pages_PublicReviewPage.konaklamanizla_ilgili_goruslerinizi_payl')}
              />
              <p className="text-xs text-gray-400 text-right mt-1">{comment.length} / 2000</p>
            </div>

            {error && (
              <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3 flex items-start gap-2">
                <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <Button
              onClick={submit}
              disabled={!rating || submitting}
              className="w-full"
              size="lg"
            >
              {submitting ? (
                <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> {t('cm.pages_PublicReviewPage.gonderiliyor')}</>
              ) : (
                'Değerlendirmemi Gönder'
              )}
            </Button>
          </CardContent>
        </Card>
        <p className="text-center text-xs text-gray-400 mt-4">
          {t('cm.pages_PublicReviewPage.bu_degerlendirme_yalnizca')} {invite?.hotel_name || 'otel'} {t('cm.pages_PublicReviewPage.ile_paylasilacaktir')}
        </p>
      </div>
    </div>
  );
};

export default PublicReviewPage;
