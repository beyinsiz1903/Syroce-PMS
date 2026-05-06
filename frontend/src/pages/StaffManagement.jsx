import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Users, Calendar, TrendingUp, Award, Home, UserPlus, Clock } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

const StaffManagement = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [staff, setStaff] = useState([]);

  useEffect(() => {
    loadStaff();
  }, []);

  const loadStaff = async () => {
    try {
      const response = await axios.get('/hr/staff');
      setStaff(response.data.staff || []);
    } catch (error) {
      console.error('Personel listesi yüklenemedi');
    }
  };

  return (
    <div className="p-6">
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <Button 
            variant="outline" 
            size="icon"
            onClick={() => navigate('/')}
            className="hover:bg-green-50"
          >
            <Home className="w-5 h-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">{t('staffMgmt.title')}</h1>
            <p className="text-gray-600">{t('staffMgmt.subtitle')}</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-6 text-center">
            <Users className="w-8 h-8 text-blue-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">{staff.length}</p>
            <p className="text-sm text-gray-500">{t('staffMgmt.activeStaff')}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <Calendar className="w-8 h-8 text-green-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">0</p>
            <p className="text-sm text-gray-500">{t('staffMgmt.todayShift')}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <TrendingUp className="w-8 h-8 text-indigo-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">8.5</p>
            <p className="text-sm text-gray-500">{t('staffMgmt.avgPerformance')}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <Award className="w-8 h-8 text-yellow-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">12</p>
            <p className="text-sm text-gray-500">{t('staffMgmt.employeeOfMonth')}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t('staffMgmt.staffList')}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {staff.length === 0 ? (
              <p className="text-center text-gray-600 py-8">{t('staffMgmt.noStaff')}</p>
            ) : (
              staff.map((member) => (
                <div key={member.id} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                  <div>
                    <p className="font-semibold">{member.name}</p>
                    <p className="text-sm text-gray-600 capitalize">{member.department} - {member.position}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm text-gray-500">{t('staffMgmt.performance')}</p>
                    <p className="text-lg font-bold text-green-600">{member.performance_score || 0}/10</p>
                  </div>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default StaffManagement;