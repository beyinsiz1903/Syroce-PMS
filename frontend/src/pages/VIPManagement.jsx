import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import {
  Crown, Star, Shield, AlertTriangle, Gift, Cake, 
  Heart, User, Mail, Phone, Calendar, TrendingUp, Home, UserPlus 
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const VIPManagement = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [vipGuests, setVipGuests] = useState([]);
  const [upcomingCelebrations, setUpcomingCelebrations] = useState([]);
  const [selectedGuest, setSelectedGuest] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadVIPGuests();
    loadUpcomingCelebrations();
  }, []);

  const loadVIPGuests = async () => {
    try {
      const response = await axios.get('/vip/list');
      setVipGuests(response.data.vip_guests || []);
    } catch (error) {
      toast.error('VIP listesi yüklenemedi');
    }
  };

  const loadUpcomingCelebrations = async () => {
    try {
      const response = await axios.get('/celebrations/upcoming?days=30');
      setUpcomingCelebrations(response.data.upcoming_celebrations || []);
    } catch (error) {
      console.error('Kutlamalar yüklenemedi');
    }
  };

  const VIPTierBadge = ({ tier }) => {
    const config = {
      platinum: { color: 'bg-purple-100 text-purple-800 border-purple-300', icon: Crown, label: 'Platinum' },
      gold: { color: 'bg-yellow-100 text-yellow-800 border-yellow-300', icon: Star, label: 'Gold' },
      silver: { color: 'bg-gray-100 text-gray-800 border-gray-300', icon: Shield, label: 'Silver' },
      regular: { color: 'bg-blue-100 text-blue-800 border-blue-300', icon: User, label: 'Regular' }
    };

    const { color, icon: Icon, label } = config[tier] || config.regular;

    return (
      <Badge className={`${color} border-2 px-3 py-1`}>
        <Icon className="w-4 h-4 mr-1" />
        {label}
      </Badge>
    );
  };

  const CelebrationCard = ({ celebration }) => {
    const icons = {
      birthday: { icon: Cake, color: 'text-pink-600', bg: 'bg-pink-50' },
      anniversary: { icon: Heart, color: 'text-red-600', bg: 'bg-red-50' }
    };

    const { icon: Icon, color, bg } = icons[celebration.type] || icons.birthday;

    return (
      <Card className={`${bg} border-2`}>
        <CardContent className="pt-4">
          <div className="flex items-center gap-3">
            <div className={`p-3 rounded-full ${bg}`}>
              <Icon className={`w-6 h-6 ${color}`} />
            </div>
            <div className="flex-1">
              <p className="font-semibold text-gray-900">{celebration.guest_name}</p>
              <p className="text-sm text-gray-600">
                {celebration.type === 'birthday' ? '🎂 Doğum Günü' : '💑 Yıldönümü'} - 
                {new Date(celebration.date).toLocaleDateString('tr-TR')}
              </p>
            </div>
            <div className="text-right">
              <p className={`text-2xl font-bold ${color}`}>
                {celebration.days_until}
              </p>
              <p className="text-xs text-gray-500">gün kaldı</p>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  };

  return (
    <div className="p-6">
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <Button 
            variant="outline" 
            size="icon"
            onClick={() => navigate('/')}
            className="hover:bg-purple-50"
          >
            <Home className="w-5 h-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">
              👑 VIP Misafir Yönetimi
            </h1>
            <p className="text-gray-600">
              VIP profiller, özel protokoller ve kutlama takibi
            </p>
          </div>
        </div>
      </div>

      <Tabs defaultValue="vip-list" className="space-y-6">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="vip-list">
            <Crown className="w-4 h-4 mr-2" />
            VIP Listesi
          </TabsTrigger>
          <TabsTrigger value="celebrations">
            <Cake className="w-4 h-4 mr-2" />
            Yaklaşan Kutlamalar
          </TabsTrigger>
          <TabsTrigger value="blacklist">
            <AlertTriangle className="w-4 h-4 mr-2" />
            Blacklist
          </TabsTrigger>
        </TabsList>

        {/* VIP List */}
        <TabsContent value="vip-list" className="space-y-4">
          {/* Add VIP Button */}
          <div className="flex justify-end mb-4">
            <Dialog>
              <DialogTrigger asChild>
                <Button className="bg-purple-600 hover:bg-purple-700">
                  <UserPlus className="w-4 h-4 mr-2" />
                  Yeni VIP Ekle
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl">
                <DialogHeader>
                  <DialogTitle>VIP Protokol Oluştur</DialogTitle>
                </DialogHeader>
                <form className="space-y-4 mt-4" onSubmit={async (e) => {
                  e.preventDefault();
                  const formData = new FormData(e.target);
                  try {
                    await axios.post('/guests/search-guest-id/vip-protocol', {
                      vip_tier: formData.get('tier'),
                      special_handling_notes: formData.get('notes'),
                      welcome_amenities: formData.get('amenities')?.split(',') || [],
                      early_checkin_guaranteed: formData.get('early_checkin') === 'on'
                    });
                    toast.success('VIP protokol oluşturuldu!');
                    loadVIPGuests();
                  } catch (error) {
                    toast.error('VIP oluşturulamadı');
                  }
                }}>
                  <div>
                    <Label>Misafir ID veya Email</Label>
                    <Input name="guest_search" placeholder="Misafir ara..." required />
                  </div>
                  <div>
                    <Label>VIP Tier</Label>
                    <select name="tier" className="w-full px-3 py-2 border rounded-lg">
                      <option value="platinum">Platinum</option>
                      <option value="gold">Gold</option>
                      <option value="silver">Silver</option>
                    </select>
                  </div>
                  <div>
                    <Label>Özel Notlar</Label>
                    <Textarea name="notes" placeholder="Özel talimatlar, tercihler..." rows={3} />
                  </div>
                  <div>
                    <Label>Welcome Amenities (virgülle ayırın)</Label>
                    <Input name="amenities" placeholder="Champagne, Flowers, Fruit Basket" />
                  </div>
                  <div className="flex items-center gap-2">
                    <input type="checkbox" name="early_checkin" id="early_checkin" className="w-4 h-4" />
                    <Label htmlFor="early_checkin">Erken Check-in Garantisi</Label>
                  </div>
                  <Button type="submit" className="w-full">VIP Protokol Oluştur</Button>
                </form>
              </DialogContent>
            </Dialog>
          </div>

          {vipGuests.length === 0 ? (
            <Card>
              <CardContent className="pt-12 pb-12 text-center">
                <Crown className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-600">Henüz VIP misafir yok</p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {vipGuests.map((vip) => (
                <Card key={vip.guest_id} className="hover:shadow-lg transition-shadow cursor-pointer">
                  <CardContent className="pt-6">
                    <div className="flex items-start justify-between mb-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <h3 className="text-lg font-bold">{vip.guest_name}</h3>
                          <VIPTierBadge tier={vip.vip_tier} />
                        </div>
                        <div className="space-y-1 text-sm text-gray-600">
                          <div className="flex items-center gap-2">
                            <Mail className="w-4 h-4" />
                            {vip.guest_email}
                          </div>
                          {vip.guest_phone && (
                            <div className="flex items-center gap-2">
                              <Phone className="w-4 h-4" />
                              {vip.guest_phone}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    {vip.special_handling_notes && (
                      <div className="mt-3 p-3 bg-yellow-50 rounded-lg border border-yellow-200">
                        <p className="text-sm text-yellow-800">
                          <strong>⚠️ Özel Not:</strong> {vip.special_handling_notes}
                        </p>
                      </div>
                    )}

                    {vip.welcome_amenities && vip.welcome_amenities.length > 0 && (
                      <div className="mt-3">
                        <p className="text-xs text-gray-500 mb-1">Welcome Amenities:</p>
                        <div className="flex flex-wrap gap-1">
                          {vip.welcome_amenities.map((amenity, idx) => (
                            <Badge key={idx} variant="outline" className="text-xs">
                              {amenity}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {/* Statistics */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-6">
            <Card>
              <CardContent className="pt-6 text-center">
                <Crown className="w-8 h-8 text-purple-600 mx-auto mb-2" />
                <p className="text-2xl font-bold">
                  {vipGuests.filter(v => v.vip_tier === 'platinum').length}
                </p>
                <p className="text-sm text-gray-500">Platinum</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6 text-center">
                <Star className="w-8 h-8 text-yellow-600 mx-auto mb-2" />
                <p className="text-2xl font-bold">
                  {vipGuests.filter(v => v.vip_tier === 'gold').length}
                </p>
                <p className="text-sm text-gray-500">Gold</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6 text-center">
                <Shield className="w-8 h-8 text-gray-600 mx-auto mb-2" />
                <p className="text-2xl font-bold">
                  {vipGuests.filter(v => v.vip_tier === 'silver').length}
                </p>
                <p className="text-sm text-gray-500">Silver</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6 text-center">
                <TrendingUp className="w-8 h-8 text-blue-600 mx-auto mb-2" />
                <p className="text-2xl font-bold">{vipGuests.length}</p>
                <p className="text-sm text-gray-500">Toplam VIP</p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Upcoming Celebrations */}
        <TabsContent value="celebrations" className="space-y-4">
          {upcomingCelebrations.length === 0 ? (
            <Card>
              <CardContent className="pt-12 pb-12 text-center">
                <Cake className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-600">Önümüzdeki 30 günde kutlama yok</p>
              </CardContent>
            </Card>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {upcomingCelebrations.map((celeb, idx) => (
                  <CelebrationCard key={idx} celebration={celeb} />
                ))}
              </div>

              <Card className="bg-blue-50 border-blue-200">
                <CardContent className="pt-6">
                  <div className="flex items-center gap-3">
                    <Gift className="w-8 h-8 text-blue-600" />
                    <div>
                      <p className="font-semibold text-gray-900">
                        Otomatik Kutlama Hatırlatıcıları
                      </p>
                      <p className="text-sm text-gray-600">
                        Kutlamalardan 7 gün önce otomatik hatırlatma e-postası gönderilir
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </>
          )}
        </TabsContent>

        {/* Blacklist */}
        <TabsContent value="blacklist">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-red-600">
                <AlertTriangle className="w-5 h-5" />
                Blacklist Yönetimi
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-center py-8">
                <AlertTriangle className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-600">
                  Blacklist özelliği aktif - Misafir profillerinden yönetilir
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default VIPManagement;
