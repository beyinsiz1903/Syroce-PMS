import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import Layout from '../components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { 
  DollarSign, 
  TrendingUp, 
  TrendingDown,
  Calendar,
  RefreshCw,
  Download,
  BarChart3,
  PieChart
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart as RePieChart, Pie, Cell } from 'recharts';

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8', '#82CA9D', '#FFC658', '#FF6B6B'];

const CATEGORY_LABELS = {
  salaries: 'Maaşlar',
  utilities: 'Faturalar',
  supplies: 'Malzemeler',
  maintenance: 'Bakım',
  marketing: 'Pazarlama',
  rent: 'Kira',
  insurance: 'Sigorta',
  taxes: 'Vergiler',
  other: 'Diğer',
};

const CostManagement = ({ user, tenant, onLogout }) => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [costData, setCostData] = useState(null);

  useEffect(() => {
    loadCostData();
  }, []);

  const loadCostData = async () => {
    try {
      setLoading(true);
      const [dashRes, expensesRes] = await Promise.all([
        axios.get('/accounting/dashboard'),
        axios.get('/accounting/expenses'),
      ]);
      const dashboard = dashRes.data || {};
      const expenses = expensesRes.data || [];

      const byCategory = {};
      let totalCosts = 0;
      expenses.forEach(exp => {
        const cat = exp.category || 'other';
        if (!byCategory[cat]) byCategory[cat] = { total: 0, count: 0 };
        const amount = exp.total_amount || exp.amount || 0;
        byCategory[cat].total += amount;
        byCategory[cat].count += 1;
        totalCosts += amount;
      });

      setCostData({
        total_costs: totalCosts || dashboard.monthly_expenses || 0,
        entries_count: expenses.length,
        by_category: byCategory,
        monthly_income: dashboard.monthly_income || 0,
        net_income: dashboard.net_income || 0,
      });
    } catch (error) {
      console.error('Maliyet verileri yüklenemedi:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="cost-management">
        <div className="flex items-center justify-center h-screen">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-600" />
        </div>
      </Layout>
    );
  }

  if (!costData) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout}>
        <div className="p-6">
          <div className="text-center text-gray-600">Maliyet verisi bulunamadı</div>
        </div>
      </Layout>
    );
  }

  const categoryData = Object.entries(costData.by_category).map(([name, data]) => ({
    name: CATEGORY_LABELS[name] || name,
    total: data.total,
    count: data.count,
    avg: data.count > 0 ? data.total / data.count : 0,
  }));

  const pieData = categoryData.map(cat => ({
    name: cat.name,
    value: cat.total,
  }));

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="cost-management">
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <DollarSign className="w-8 h-8 text-red-600" />
              Maliyet Yönetimi
            </h1>
            <p className="text-gray-600 mt-1">Operasyonel giderleri takip edin ve analiz edin</p>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" onClick={loadCostData}>
              <RefreshCw className="w-4 h-4 mr-2" />
              Yenile
            </Button>
            <Button variant="outline">
              <Download className="w-4 h-4 mr-2" />
              Dışa Aktar
            </Button>
            <Button onClick={() => navigate('/')}>
              Ana Sayfa
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <Card className="bg-gradient-to-br from-red-50 to-red-100 border-red-200">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-red-600 font-medium">Toplam Giderler</p>
                  <p className="text-3xl font-bold text-red-700 mt-2">
                    ₺{costData.total_costs.toLocaleString('tr-TR')}
                  </p>
                  <p className="text-xs text-red-600 mt-1">Bu ay</p>
                </div>
                <TrendingDown className="w-12 h-12 text-red-300" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-blue-50 to-blue-100 border-blue-200">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-blue-600 font-medium">Kategoriler</p>
                  <p className="text-3xl font-bold text-blue-700 mt-2">
                    {Object.keys(costData.by_category).length}
                  </p>
                  <p className="text-xs text-blue-600 mt-1">Gider kategorisi</p>
                </div>
                <PieChart className="w-12 h-12 text-blue-300" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-green-50 to-green-100 border-green-200">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-green-600 font-medium">Kayıtlar</p>
                  <p className="text-3xl font-bold text-green-700 mt-2">
                    {costData.entries_count}
                  </p>
                  <p className="text-xs text-green-600 mt-1">Toplam işlem</p>
                </div>
                <BarChart3 className="w-12 h-12 text-green-300" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-purple-50 to-purple-100 border-purple-200">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-purple-600 font-medium">Günlük Ortalama</p>
                  <p className="text-3xl font-bold text-purple-700 mt-2">
                    ₺{(costData.total_costs / 30).toFixed(0)}
                  </p>
                  <p className="text-xs text-purple-600 mt-1">Günlük gider ortalaması</p>
                </div>
                <Calendar className="w-12 h-12 text-purple-300" />
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center">
                <BarChart3 className="w-5 h-5 mr-2 text-blue-600" />
                Kategoriye Göre Giderler
              </CardTitle>
            </CardHeader>
            <CardContent>
              {categoryData.length === 0 ? (
                <div className="text-center text-gray-400 py-12">Gider kaydı yok</div>
              ) : (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={categoryData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" angle={-45} textAnchor="end" height={100} />
                    <YAxis />
                    <Tooltip formatter={(value) => `₺${value.toLocaleString('tr-TR')}`} />
                    <Legend />
                    <Bar dataKey="total" fill="#3B82F6" name="Toplam Gider" />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center">
                <PieChart className="w-5 h-5 mr-2 text-purple-600" />
                Gider Dağılımı
              </CardTitle>
            </CardHeader>
            <CardContent>
              {pieData.length === 0 ? (
                <div className="text-center text-gray-400 py-12">Gider kaydı yok</div>
              ) : (
                <ResponsiveContainer width="100%" height={300}>
                  <RePieChart>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, percent }) => `${name}: %${(percent * 100).toFixed(0)}`}
                      outerRadius={100}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {pieData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value) => `₺${value.toLocaleString('tr-TR')}`} />
                  </RePieChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Kategori Detayları</CardTitle>
          </CardHeader>
          <CardContent>
            {categoryData.length === 0 ? (
              <div className="text-center text-gray-400 py-8">Henüz gider kaydı yok</div>
            ) : (
              <div className="space-y-3">
                {categoryData.sort((a, b) => b.total - a.total).map((cat, idx) => {
                  const percentage = costData.total_costs > 0 ? ((cat.total / costData.total_costs) * 100).toFixed(1) : '0';
                  return (
                    <div key={idx} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition">
                      <div className="flex items-center space-x-4 flex-1">
                        <div
                          className="w-4 h-4 rounded"
                          style={{ backgroundColor: COLORS[idx % COLORS.length] }}
                        />
                        <div className="flex-1">
                          <p className="font-semibold text-gray-900">{cat.name}</p>
                          <p className="text-sm text-gray-600">{cat.count} işlem</p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-lg font-bold text-gray-900">₺{cat.total.toLocaleString('tr-TR')}</p>
                        <Badge variant="outline" className="mt-1">
                          %{percentage}
                        </Badge>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200">
          <CardContent className="p-4">
            <div className="flex items-start space-x-3">
              <div className="bg-blue-100 p-2 rounded-full">
                <DollarSign className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <h4 className="font-semibold text-gray-900 mb-1">Maliyet Analizi</h4>
                <p className="text-sm text-gray-600">
                  Operasyonel giderlerinizi kategorilere göre takip edin. 
                  {categoryData.length > 0 && (
                    <>
                      {' '}En büyük gider kalemi: <strong>{categoryData[0]?.name}</strong> (₺{categoryData[0]?.total.toLocaleString('tr-TR')}).
                      {' '}Günlük ortalama gider: <strong>₺{(costData.total_costs / 30).toFixed(0)}</strong>.
                    </>
                  )}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
};

export default CostManagement;
