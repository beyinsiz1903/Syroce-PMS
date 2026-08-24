import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Star, RefreshCw, MessageSquareText } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';

export default function ReputationManager() {
  const [overview, setOverview] = useState(null);
  const [reviews, setReviews] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [overviewResponse, reviewsResponse] = await Promise.all([
        axios.get('/reputation/overview'),
        axios.get('/reputation/reviews', { params: { limit: 100 } })
      ]);
      setOverview(overviewResponse.data);
      setReviews(reviewsResponse.data.reviews || []);
    } catch (error) {
      setMessage(error.response?.data?.detail || 'İtibar verileri yüklenemedi.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const suggest = async (review) => {
    const response = await axios.post('/reputation/suggest-response', {
      review_text: review.review_text,
      rating: review.rating
    });
    setDrafts(current => ({ ...current, [review.id]: response.data.suggested_response }));
  };

  const saveResponse = async (review) => {
    const responseText = (drafts[review.id] || '').trim();
    if (!responseText) {
      setMessage('Kaydedilecek yanıt boş olamaz.');
      return;
    }
    await axios.post(`/reputation/reviews/${review.id}/response`, { response_text: responseText });
    setMessage('Yanıt Syroce içinde kaydedildi; dış platforma otomatik gönderilmedi.');
    await load();
  };

  return <div className="space-y-6">
    <div className="flex items-center justify-between">
      <div><h2 className="text-2xl font-bold">İtibar Yönetimi</h2><p className="text-sm text-gray-500">Platform yorumları, eğilimler ve denetimli yanıt taslakları</p></div>
      <Button variant="outline" onClick={load} disabled={loading}><RefreshCw className="w-4 h-4 mr-2" />Yenile</Button>
    </div>
    {message && <div className="rounded-lg bg-blue-50 p-3 text-sm text-blue-700">{message}</div>}
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <Card><CardContent className="pt-6"><div className="text-3xl font-bold">{overview?.overall_rating ?? '—'} <Star className="inline w-5 h-5 text-amber-500" /></div><p className="text-sm text-gray-500">Genel Puan / 5</p></CardContent></Card>
      <Card><CardContent className="pt-6"><div className="text-3xl font-bold">{overview?.total_reviews || 0}</div><p className="text-sm text-gray-500">Toplam Yorum</p></CardContent></Card>
      <Card><CardContent className="pt-6"><div className="text-3xl font-bold">{overview?.responded_reviews || 0}</div><p className="text-sm text-gray-500">Yanıtlanan</p></CardContent></Card>
    </div>
    {!overview?.data_available && <Card><CardContent className="py-8 text-center text-gray-500">{overview?.message || 'Henüz değerlendirme verisi yok.'}</CardContent></Card>}
    <div className="space-y-3">
      {reviews.map(review => <Card key={review.id}>
        <CardHeader className="pb-3"><div className="flex justify-between gap-4"><CardTitle className="text-base">{review.author_name || 'Misafir'} · {review.platform}</CardTitle><Badge variant={review.response_status === 'responded' ? 'default' : 'outline'}>{review.response_status === 'responded' ? 'Yanıtlandı' : 'Yanıt Bekliyor'}</Badge></div></CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-2 text-sm"><Star className="w-4 h-4 text-amber-500" />{review.rating_5 ?? review.rating}/5</div>
          <p className="text-sm text-gray-700">{review.review_text}</p>
          {review.response_status === 'responded' ? <div className="rounded-lg bg-green-50 p-3 text-sm text-green-800"><strong>Kayıtlı yanıt:</strong> {review.response_text}</div> : <>
            <Input value={drafts[review.id] || ''} onChange={event => setDrafts(current => ({ ...current, [review.id]: event.target.value }))} placeholder="Yanıt taslağı" />
            <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => suggest(review)}><MessageSquareText className="w-4 h-4 mr-2" />Taslak Öner</Button><Button onClick={() => saveResponse(review)}>Yanıtı Kaydet</Button></div>
          </>}
        </CardContent>
      </Card>)}
    </div>
  </div>;
}
