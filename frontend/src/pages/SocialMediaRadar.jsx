import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Home, Instagram, Twitter, Facebook, TrendingUp, AlertTriangle, Heart, MessageCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const SocialMediaRadar = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [mentions, setMentions] = useState([]);
  const [sentiment, setSentiment] = useState(null);
  const [alerts, setAlerts] = useState([]);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [mentionsRes, sentimentRes, alertsRes] = await Promise.all([
        axios.get('/social-media/mentions?hours=24'),
        axios.get('/social-media/sentiment?days=7'),
        axios.get('/social-media/crisis-alerts')
      ]);
      setMentions(mentionsRes.data.mentions || []);
      setSentiment(sentimentRes.data);
      setAlerts(alertsRes.data.alerts || []);
    } catch (error) {
      console.error('Social media data yüklenemedi');
    }
  };

  const getPlatformIcon = (platform) => {
    switch(platform) {
      case 'instagram': return <Instagram className="w-5 h-5 text-pink-600" />;
      case 'twitter': return <Twitter className="w-5 h-5 text-blue-600" />;
      case 'facebook': return <Facebook className="w-5 h-5 text-blue-700" />;
      default: return <MessageCircle className="w-5 h-5" />;
    }
  };

  return (
    <div className="p-6">
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <Button variant="outline" size="icon" onClick={() => navigate('/')} className="hover:bg-pink-50">
            <Home className="w-5 h-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">{t('aiModule.socialRadar')}</h1>
            <p className="text-gray-600">{t('aiModule.socialRadarDesc')}</p>
          </div>
        </div>
      </div>

      {/* Crisis Alerts */}
      {alerts.length > 0 && (
        <Card className="mb-6 border-2 border-red-500 bg-red-50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-red-800">
              <AlertTriangle className="w-6 h-6" />
              KRİZ UYARISI!
            </CardTitle>
          </CardHeader>
          <CardContent>
            {alerts.map((alert, idx) => (
              <div key={idx} className="bg-white p-4 rounded-lg">
                <p className="font-bold text-red-600">{alert.description}</p>
                <p className="text-sm mt-2">{alert.recommended_action}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Sentiment Summary */}
      {sentiment && (
        <div className="grid grid-cols-4 gap-4 mb-6">
          <Card>
            <CardContent className="pt-6 text-center">
              <MessageCircle className="w-10 h-10 text-blue-600 mx-auto mb-2" />
              <p className="text-3xl font-bold">{sentiment.total_mentions}</p>
              <p className="text-sm text-gray-600">Toplam Mention</p>
            </CardContent>
          </Card>
          <Card className="bg-green-50">
            <CardContent className="pt-6 text-center">
              <Heart className="w-10 h-10 text-green-600 mx-auto mb-2" />
              <p className="text-3xl font-bold">{sentiment.positive}</p>
              <p className="text-sm text-gray-600">Positive</p>
            </CardContent>
          </Card>
          <Card className="bg-yellow-50">
            <CardContent className="pt-6 text-center">
              <MessageCircle className="w-10 h-10 text-yellow-600 mx-auto mb-2" />
              <p className="text-3xl font-bold">{sentiment.neutral}</p>
              <p className="text-sm text-gray-600">Neutral</p>
            </CardContent>
          </Card>
          <Card className="bg-red-50">
            <CardContent className="pt-6 text-center">
              <AlertTriangle className="w-10 h-10 text-red-600 mx-auto mb-2" />
              <p className="text-3xl font-bold">{sentiment.negative}</p>
              <p className="text-sm text-gray-600">Negative</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Recent Mentions */}
      <Card>
        <CardHeader>
          <CardTitle>Son Mention'lar (24 Saat)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {mentions.map((mention) => (
              <div key={mention.id} className={`p-4 rounded-lg border-l-4 ${
                mention.sentiment === 'positive' ? 'bg-green-50 border-green-500' :
                mention.sentiment === 'negative' ? 'bg-red-50 border-red-500' :
                'bg-gray-50 border-gray-500'
              }`}>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      {getPlatformIcon(mention.platform)}
                      <span className="font-semibold">@{mention.username}</span>
                      <Badge className={mention.sentiment === 'positive' ? 'bg-green-600' : mention.sentiment === 'negative' ? 'bg-red-600' : 'bg-gray-600'}>
                        {mention.sentiment}
                      </Badge>
                    </div>
                    <p className="text-sm">{mention.text}</p>
                    <p className="text-xs text-gray-500 mt-2">
                      {new Date(mention.posted_at).toLocaleString('tr-TR')} • {mention.engagement} engagement
                    </p>
                  </div>
                  <Button size="sm" variant="outline">
                    Yanıtla
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default SocialMediaRadar;