import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { 
import { useTranslation } from 'react-i18next';
  Home, 
  Bed, 
  Users, 
  UtensilsCrossed, 
  Wrench, 
  DollarSign, 
  BarChart3,
  ArrowLeft,
  Menu,
  Smartphone,
  Shield
} from 'lucide-react';

const MobileDashboard = ({ user, onLogout }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [showMenu, setShowMenu] = useState(false);

  const departments = [
    {
      id: 'housekeeping',
      name: 'Temizlik Yönetimi',
      nameEn: 'Housekeeping',
      icon: Bed,
      color: 'bg-blue-500',
      roles: ['ADMIN', 'SUPERVISOR', 'HOUSEKEEPING'],
      path: '/mobile/housekeeping'
    },
    {
      id: 'frontdesk',
      name: 'Ön Büro',
      nameEn: 'Front Desk',
      icon: Users,
      color: 'bg-green-500',
      roles: ['ADMIN', 'SUPERVISOR', 'FRONT_DESK'],
      path: '/mobile/frontdesk'
    },
    {
      id: 'fnb',
      name: 'Yiyecek & İçecek',
      nameEn: 'F&B',
      icon: UtensilsCrossed,
      color: 'bg-orange-500',
      roles: ['ADMIN', 'SUPERVISOR', 'FNB'],
      path: '/mobile/fnb'
    },
    {
      id: 'maintenance',
      name: 'Teknik Servis',
      nameEn: 'Maintenance',
      icon: Wrench,
      color: 'bg-purple-500',
      roles: ['ADMIN', 'SUPERVISOR', 'MAINTENANCE'],
      path: '/mobile/maintenance'
    },
    {
      id: 'finance',
      name: 'Finans',
      nameEn: 'Finance',
      icon: DollarSign,
      color: 'bg-teal-500',
      roles: ['ADMIN', 'SUPERVISOR', 'FINANCE'],
      path: '/mobile/finance'
    },
    {
      id: 'revenue',
      name: 'Gelir Yönetimi',
      nameEn: 'Revenue Management',
      icon: BarChart3,
      color: 'bg-indigo-600',
      roles: ['ADMIN', 'SUPERVISOR', 'FINANCE'],
      path: '/mobile/revenue'
    },
    {
      id: 'gm',
      name: 'Genel Müdür',
      nameEn: 'General Manager',
      icon: BarChart3,
      color: 'bg-red-500',
      roles: ['ADMIN', 'SUPERVISOR'],
      path: '/mobile/gm'
    },
    {
      id: 'security',
      name: 'Güvenlik & IT',
      nameEn: 'Security & IT',
      icon: Shield,
      color: 'bg-gray-700',
      roles: ['ADMIN', 'SUPERVISOR', 'IT'],
      path: '/mobile/security'
    }
  ];

  // Filter departments based on user role
  const availableDepartments = departments.filter(dept => 
    dept.roles.includes(user?.role?.toUpperCase() || '')
  );

  const handleDepartmentClick = (path) => {
    navigate(path);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 text-white p-4 sticky top-0 z-50 shadow-lg">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center space-x-3">
            <Smartphone className="w-8 h-8" />
            <div>
              <h1 className="text-xl font-bold">Mobil Yönetim</h1>
              <p className="text-xs text-blue-100">Departman Seçin</p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/')}
              className="text-white hover:bg-white/20"
            >
              <Home className="w-4 h-4 mr-1" />
              Ana Sayfa
            </Button>
          </div>
        </div>
      </div>

      {/* User Info */}
      <div className="max-w-7xl mx-auto p-4">
        <Card className="mb-4 bg-white/80 backdrop-blur">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">Hoş geldiniz,</p>
                <p className="text-lg font-bold text-gray-900">{user?.name || 'Kullanıcı'}</p>
                <p className="text-sm text-blue-600">{user?.role || 'Role'}</p>
              </div>
              <div className="text-right">
                <p className="text-xs text-gray-500">Bugün</p>
                <p className="text-sm font-semibold">{new Date().toLocaleDateString('tr-TR')}</p>
              </div>
            </div>
          </CardContent>
        </Card>


        {/* Quick Actions Bar */}
        <div className="grid grid-cols-4 gap-2 mb-4">
          <Button 
            variant="outline" 
            className="flex flex-col items-center py-4 h-auto"
            onClick={() => navigate('/reservation-calendar')}
          >
            <Home className="w-6 h-6 mb-1" />
            <span className="text-xs">Calendar</span>
          </Button>
          <Button 
            variant="outline" 
            className="flex flex-col items-center py-4 h-auto"
            onClick={() => navigate('/pms')}
          >
            <Users className="w-6 h-6 mb-1" />
            <span className="text-xs">PMS</span>
          </Button>
          <Button 
            variant="outline" 
            className="flex flex-col items-center py-4 h-auto"
            onClick={() => navigate('/invoices')}
          >
            <DollarSign className="w-6 h-6 mb-1" />
            <span className="text-xs">Invoices</span>
          </Button>
          <Button 
            variant="outline" 
            className="flex flex-col items-center py-4 h-auto relative"
            onClick={() => navigate('/mobile/gm')}
          >
            <BarChart3 className="w-6 h-6 mb-1" />
            <span className="text-xs">Reports</span>
          </Button>
        </div>

        {/* Today's Notifications */}
        <Card className="mb-4 border-orange-200 bg-orange-50">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              🔔 Today's Alerts
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex items-center justify-between p-2 bg-white rounded">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
                <span className="text-sm">12 rooms need cleaning</span>
              </div>
              <Button size="sm" variant="ghost" onClick={() => navigate('/mobile/housekeeping')}>
                View
              </Button>
            </div>
            <div className="flex items-center justify-between p-2 bg-white rounded">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                <span className="text-sm">8 arrivals expected</span>
              </div>
              <Button size="sm" variant="ghost" onClick={() => navigate('/mobile/frontdesk')}>
                View
              </Button>
            </div>
            <div className="flex items-center justify-between p-2 bg-white rounded">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                <span className="text-sm">5 pending requests</span>
              </div>
              <Button size="sm" variant="ghost" onClick={() => navigate('/mobile/maintenance')}>
                View
              </Button>
            </div>
          </CardContent>
        </Card>


        {/* Departments Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {availableDepartments.map((dept) => {
            const Icon = dept.icon;
            return (
              <Card
                key={dept.id}
                className="hover:shadow-2xl transition-all duration-300 cursor-pointer transform hover:scale-105 bg-white overflow-hidden"
                onClick={() => handleDepartmentClick(dept.path)}
              >
                <CardContent className="p-0">
                  <div className={`${dept.color} p-6 text-white`}>
                    <Icon className="w-12 h-12 mb-3" />
                  </div>
                  <div className="p-4">
                    <h3 className="text-lg font-bold text-gray-900 mb-1">{dept.name}</h3>
                    <p className="text-sm text-gray-600">{dept.nameEn}</p>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        {availableDepartments.length === 0 && (
          <Card className="mt-8">
            <CardContent className="p-8 text-center">
              <p className="text-gray-600">Bu kullanıcı için erişilebilir departman bulunmamaktadır.</p>
            </CardContent>
          </Card>
        )}

        {/* Info Card */}
        <Card className="mt-6 bg-gradient-to-r from-blue-50 to-indigo-50">
          <CardContent className="p-4">
            <div className="flex items-start space-x-3">
              <div className="bg-blue-100 p-2 rounded-full">
                <Smartphone className="w-5 h-5 text-blue-600" />
              </div>
              <div className="flex-1">
                <h4 className="font-semibold text-gray-900 mb-1">📱 Mobil Optimize</h4>
                <p className="text-sm text-gray-600">
                  Her departman mobil cihazlar için optimize edilmiştir. 
                  Hızlı erişim ve kolay kullanım için tasarlandı.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default MobileDashboard;