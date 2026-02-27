import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Gift, Star, Award, Home, TrendingUp, Users, Trophy } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

const AdvancedLoyalty = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [stats, setStats] = useState({
    total_members: 0,
    gold_members: 0,
    total_points_issued: 0,
    redemptions_this_month: 0
  });

  return (
    <div className="p-6">
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <Button 
            variant="outline" 
            size="icon"
            onClick={() => navigate('/')}
            className="hover:bg-yellow-50"
          >
            <Home className="w-5 h-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">🎯 Advanced Loyalty Program</h1>
            <p className="text-gray-600">Sadakat programı, tier yönetimi ve gamification</p>
          </div>
        </div>
      </div>

      {/* Tier Breakdown */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <Card className="border-2 border-purple-200 bg-purple-50">
          <CardContent className="pt-6 text-center">
            <Trophy className="w-12 h-12 text-purple-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">Diamond</p>
            <p className="text-sm text-gray-500">0 üye</p>
          </CardContent>
        </Card>
        <Card className="border-2 border-yellow-200 bg-yellow-50">
          <CardContent className="pt-6 text-center">
            <Award className="w-12 h-12 text-yellow-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">Gold</p>
            <p className="text-sm text-gray-500">{stats.gold_members} üye</p>
          </CardContent>
        </Card>
        <Card className="border-2 border-gray-200 bg-gray-50">
          <CardContent className="pt-6 text-center">
            <Star className="w-12 h-12 text-gray-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">Silver</p>
            <p className="text-sm text-gray-500">0 üye</p>
          </CardContent>
        </Card>
        <Card className="border-2 border-orange-200 bg-orange-50">
          <CardContent className="pt-6 text-center">
            <Gift className="w-12 h-12 text-orange-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">Bronze</p>
            <p className="text-sm text-gray-500">0 üye</p>
          </CardContent>
        </Card>
      </div>

      {/* Program Features */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Puan Kazanma Kuralları</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                <span>Konaklama (€1 = 1 puan)</span>
                <span className="font-bold text-green-600">+1 puan/€</span>
              </div>
              <div className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                <span>Doğum günü bonus</span>
                <span className="font-bold text-green-600">+500 puan</span>
              </div>
              <div className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                <span>Arkadaş getir</span>
                <span className="font-bold text-green-600">+250 puan</span>
              </div>
              <div className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                <span>Review yazma</span>
                <span className="font-bold text-green-600">+100 puan</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Puan Kullanım Seçenekleri</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex justify-between items-center p-3 bg-blue-50 rounded-lg">
                <span>1 Gece Bedava (Standard)</span>
                <span className="font-bold text-blue-600">5,000 puan</span>
              </div>
              <div className="flex justify-between items-center p-3 bg-blue-50 rounded-lg">
                <span>Deluxe Upgrade</span>
                <span className="font-bold text-blue-600">2,500 puan</span>
              </div>
              <div className="flex justify-between items-center p-3 bg-blue-50 rounded-lg">
                <span>Spa Paketi</span>
                <span className="font-bold text-blue-600">1,500 puan</span>
              </div>
              <div className="flex justify-between items-center p-3 bg-blue-50 rounded-lg">
                <span>F&B €50 Credit</span>
                <span className="font-bold text-blue-600">2,000 puan</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Statistics */}
      <div className="grid grid-cols-4 gap-4 mt-6">
        <Card>
          <CardContent className="pt-6 text-center">
            <Users className="w-8 h-8 text-blue-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">{stats.total_members}</p>
            <p className="text-sm text-gray-500">Toplam Üye</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <Star className="w-8 h-8 text-yellow-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">{stats.total_points_issued}</p>
            <p className="text-sm text-gray-500">Verilen Puan</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <Gift className="w-8 h-8 text-green-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">{stats.redemptions_this_month}</p>
            <p className="text-sm text-gray-500">Bu Ay Kullanım</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <TrendingUp className="w-8 h-8 text-purple-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">+15%</p>
            <p className="text-sm text-gray-500">Büyüme</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default AdvancedLoyalty;