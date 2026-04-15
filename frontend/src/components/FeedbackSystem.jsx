import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  Star, MessageCircle, ThumbsUp, RefreshCw, Send, TrendingUp
} from 'lucide-react';

const FeedbackSystem = () => {
  const [reviews, setReviews] = useState([]);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState({ avgRating: 0, totalReviews: 0, satisfaction: 0 });
  const [respondDialog, setRespondDialog] = useState(null);
  const [responseText, setResponseText] = useState('');

  const loadReviews = useCallback(async () => {
    setLoading(true);
    try {
      const response = await axios.get('/crm/reviews');
      const list = response.data?.reviews || response.data || [];
      setReviews(list);
      if (list.length > 0) {
        const avg = list.reduce((s, r) => s + (r.rating || 0), 0) / list.length;
        const sat = (list.filter(r => r.rating >= 4).length / list.length) * 100;
        setStats({ avgRating: avg.toFixed(1), totalReviews: list.length, satisfaction: sat.toFixed(0) });
      } else {
        setStats({ avgRating: 0, totalReviews: 0, satisfaction: 0 });
      }
    } catch {
      toast.error('Değerlendirmeler yüklenemedi');
    }
    setLoading(false);
  }, []);

  useEffect(() => { loadReviews(); }, [loadReviews]);

  const renderStars = (rating) => (
    <div className="flex gap-0.5">
      {Array.from({ length: 5 }, (_, i) => (
        <Star key={i} className={`w-4 h-4 ${i < rating ? 'text-yellow-400 fill-yellow-400' : 'text-gray-300'}`} />
      ))}
    </div>
  );

  const respondToReview = async () => {
    if (!responseText.trim() || !respondDialog) return;
    try {
      await axios.post(`/crm/reviews/${respondDialog}/respond`, { response: responseText });
      toast.success('Yanıt gönderildi');
      setRespondDialog(null);
      setResponseText('');
      loadReviews();
    } catch {
      toast.error('Yanıt gönderilemedi');
    }
  };

  const getRatingBadge = (rating) => {
    if (rating >= 4) return <Badge className="bg-green-100 text-green-700">Memnun</Badge>;
    if (rating >= 3) return <Badge className="bg-yellow-100 text-yellow-700">Orta</Badge>;
    return <Badge className="bg-red-100 text-red-700">Memnun Değil</Badge>;
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-2xl font-bold flex items-center gap-2">
            <MessageCircle className="w-6 h-6" /> Misafir Geri Bildirimleri
          </h3>
          <p className="text-gray-600 text-sm">Misafir değerlendirmelerini takip edin ve yanıtlayın</p>
        </div>
        <Button variant="outline" size="sm" onClick={loadReviews} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Yenile
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="bg-yellow-50 border-yellow-200">
          <CardContent className="p-5 text-center">
            <Star className="w-6 h-6 mx-auto mb-1 text-yellow-500 fill-yellow-500" />
            <p className="text-xs text-yellow-600">Ortalama Puan</p>
            <p className="text-3xl font-bold text-yellow-700">{stats.avgRating}</p>
            <div className="flex justify-center mt-1">{renderStars(Math.round(stats.avgRating))}</div>
          </CardContent>
        </Card>
        <Card className="bg-blue-50 border-blue-200">
          <CardContent className="p-5 text-center">
            <MessageCircle className="w-6 h-6 mx-auto mb-1 text-blue-500" />
            <p className="text-xs text-blue-600">Toplam Değerlendirme</p>
            <p className="text-3xl font-bold text-blue-700">{stats.totalReviews}</p>
          </CardContent>
        </Card>
        <Card className="bg-green-50 border-green-200">
          <CardContent className="p-5 text-center">
            <TrendingUp className="w-6 h-6 mx-auto mb-1 text-green-500" />
            <p className="text-xs text-green-600">Memnuniyet Oranı</p>
            <p className="text-3xl font-bold text-green-700">%{stats.satisfaction}</p>
            <p className="text-xs text-green-500">(4+ yıldız)</p>
          </CardContent>
        </Card>
      </div>

      {reviews.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-gray-500">
            <MessageCircle className="w-12 h-12 mx-auto mb-3 text-gray-300" />
            <p className="font-medium">Henüz değerlendirme yok</p>
            <p className="text-sm mt-1">Misafir değerlendirmeleri burada görünecek</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {reviews.map((review) => (
            <Card key={review.id} className="hover:shadow-lg transition">
              <CardHeader className="pb-2">
                <div className="flex justify-between items-start">
                  <div>
                    <CardTitle className="text-lg">{review.guest_name || 'Misafir'}</CardTitle>
                    <div className="flex items-center gap-2 mt-1">
                      {renderStars(review.rating)}
                      {getRatingBadge(review.rating)}
                    </div>
                  </div>
                  <span className="text-xs text-gray-500">
                    {review.created_at ? new Date(review.created_at).toLocaleDateString('tr-TR') : ''}
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-gray-700 mb-3">{review.comment}</p>
                {review.category && (
                  <Badge variant="outline" className="mb-3">{review.category}</Badge>
                )}
                {review.response ? (
                  <div className="bg-blue-50 border border-blue-200 p-3 rounded-lg">
                    <p className="text-xs font-semibold text-blue-700 mb-1">Yönetim Yanıtı:</p>
                    <p className="text-sm text-gray-700">{review.response}</p>
                  </div>
                ) : (
                  <Button size="sm" variant="outline" onClick={() => { setRespondDialog(review.id); setResponseText(''); }}>
                    <Send className="w-4 h-4 mr-2" /> Yanıtla
                  </Button>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={!!respondDialog} onOpenChange={(o) => { if (!o) setRespondDialog(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Değerlendirmeye Yanıt Ver</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Textarea
              value={responseText}
              onChange={e => setResponseText(e.target.value)}
              rows={4}
              placeholder="Yanıtınızı yazın..."
            />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setRespondDialog(null)}>İptal</Button>
              <Button onClick={respondToReview} disabled={!responseText.trim()}>
                <Send className="w-4 h-4 mr-2" /> Gönder
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default FeedbackSystem;
