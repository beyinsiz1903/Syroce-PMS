import React, { useState, useEffect } from 'react';
import { RefreshCw, FileText, Wallet, CheckCircle, AlertCircle, TrendingUp, TrendingDown, BookOpen, BarChart } from 'lucide-react';
import axios from 'axios';

// Mock data
const mockVarianceData = {
  start: "2026-07-01",
  end: "2026-07-05",
  theoretical_cost: 12450.00,
  actual_cost: 12800.50,
  variance_amount: 350.50,
  details: [
    { name: "Dana Kıyma (gr)", theoretical: 15000, actual: 15200, unit: "gr", variance: 200, cost_impact: 120.00 },
    { name: "Hamburger Ekmeği (adet)", theoretical: 100, actual: 102, unit: "adet", variance: 2, cost_impact: 10.00 },
    { name: "Patates (gr)", theoretical: 20000, actual: 20500, unit: "gr", variance: 500, cost_impact: 220.50 }
  ]
};

const mockRecipes = [
  {
    id: "r1",
    menu_item_name: "Cheeseburger Menu",
    yield_portions: 1,
    ingredients: [
      { name: "Dana Kıyma", quantity: 150, unit: "gr" },
      { name: "Hamburger Ekmeği", quantity: 1, unit: "adet" },
      { name: "Cheddar Peyniri", quantity: 20, unit: "gr" },
      { name: "Patates", quantity: 200, unit: "gr" }
    ]
  },
  {
    id: "r2",
    menu_item_name: "Sezar Salata",
    yield_portions: 1,
    ingredients: [
      { name: "Tavuk Göğsü", quantity: 120, unit: "gr" },
      { name: "Marul", quantity: 100, unit: "gr" },
      { name: "Sezar Sos", quantity: 30, unit: "ml" }
    ]
  }
];

export default function FnBCostingModule() {
  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(false);
  
  const [variance, setVariance] = useState(mockVarianceData);
  const [recipes, setRecipes] = useState(mockRecipes);
  
  const [postDialog, setPostDialog] = useState(false);
  const [posting, setPosting] = useState(false);
  const [alertMsg, setAlertMsg] = useState(null);

  const fetchVariance = async () => {
    try {
      setLoading(true);
      const res = await axios.get('/fnb-cost/variance?start=2026-07-01&end=2026-07-05');
      if (res.data) setVariance(res.data);
    } catch (err) {
      console.error('Variance error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handlePostCost = async () => {
    try {
      setPosting(true);
      const res = await axios.post('/fnb-cost/post-to-gl', {
        start: variance.start,
        end: variance.end
      });
      setAlertMsg({ type: 'success', text: res.data.message || 'Maliyet Yevmiye Fişi (740/150) başarıyla kesildi.' });
      setPostDialog(false);
    } catch (err) {
      setAlertMsg({ type: 'error', text: err.response?.data?.detail || 'Muhasebeye aktarım başarısız oldu.' });
    } finally {
      setPosting(false);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">F&B Maliyet ve Reçete (Costing)</h1>
        {activeTab === 0 && (
          <button 
            onClick={fetchVariance}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Analizi Yenile
          </button>
        )}
      </div>

      {alertMsg && (
        <div className={`p-4 rounded-md flex items-center justify-between ${alertMsg.type === 'success' ? 'bg-green-50 text-green-800 border border-green-200' : 'bg-red-50 text-red-800 border border-red-200'}`}>
          <div className="flex items-center gap-2">
            {alertMsg.type === 'error' ? <AlertCircle className="w-5 h-5" /> : <CheckCircle className="w-5 h-5" />}
            <span>{alertMsg.text}</span>
          </div>
          <button onClick={() => setAlertMsg(null)} className="text-gray-500 hover:text-gray-700">✕</button>
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-gray-200 gap-6">
        <button
          onClick={() => setActiveTab(0)}
          className={`pb-3 text-sm font-medium flex items-center gap-2 border-b-2 transition-colors ${activeTab === 0 ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}`}
        >
          <BarChart className="w-4 h-4" />
          Teorik vs Gerçek Maliyet (Variance)
        </button>
        <button
          onClick={() => setActiveTab(1)}
          className={`pb-3 text-sm font-medium flex items-center gap-2 border-b-2 transition-colors ${activeTab === 1 ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}`}
        >
          <BookOpen className="w-4 h-4" />
          Ürün Reçeteleri (Recipes)
        </button>
      </div>

      {activeTab === 0 && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-white border rounded-lg p-5 shadow-sm">
              <div className="text-sm text-gray-500 mb-1">Teorik Maliyet (Sistem)</div>
              <div className="text-2xl font-bold text-gray-900">{variance.theoretical_cost?.toLocaleString('tr-TR')} ₺</div>
            </div>
            <div className="bg-white border rounded-lg p-5 shadow-sm">
              <div className="text-sm text-gray-500 mb-1">Gerçekleşen Maliyet (Sayım)</div>
              <div className="text-2xl font-bold text-gray-900">{variance.actual_cost?.toLocaleString('tr-TR')} ₺</div>
            </div>
            <div className={`border rounded-lg p-5 shadow-sm ${variance.variance_amount > 0 ? 'bg-red-50 border-red-200' : 'bg-green-50 border-green-200'}`}>
              <div className={`text-sm mb-1 ${variance.variance_amount > 0 ? 'text-red-600' : 'text-green-600'}`}>
                {variance.variance_amount > 0 ? 'Maliyet Aşımı (Zarar)' : 'Maliyet Tasarrufu (Kâr)'}
              </div>
              <div className={`text-2xl font-bold flex items-center gap-2 ${variance.variance_amount > 0 ? 'text-red-700' : 'text-green-700'}`}>
                {variance.variance_amount > 0 ? <TrendingUp className="w-6 h-6" /> : <TrendingDown className="w-6 h-6" />}
                {Math.abs(variance.variance_amount).toLocaleString('tr-TR')} ₺
              </div>
            </div>
          </div>

          <div className="bg-white border rounded-lg shadow-sm">
            <div className="p-4 border-b flex justify-between items-center bg-gray-50 rounded-t-lg">
              <h2 className="text-lg font-bold text-gray-800">Kalem Bazlı Maliyet Sapmaları</h2>
              <button 
                onClick={() => setPostDialog(true)}
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 text-sm font-medium"
              >
                <Wallet className="w-4 h-4" />
                Satılan Malın Maliyetini (SMM) Muhasebeleştir
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="p-3 text-sm font-semibold text-gray-600">Ürün Adı</th>
                    <th className="p-3 text-sm font-semibold text-gray-600">Birim</th>
                    <th className="p-3 text-sm font-semibold text-gray-600 text-right">Teorik Tüketim</th>
                    <th className="p-3 text-sm font-semibold text-gray-600 text-right">Gerçek Tüketim</th>
                    <th className="p-3 text-sm font-semibold text-gray-600 text-right">Fark (Miktar)</th>
                    <th className="p-3 text-sm font-semibold text-gray-600 text-right">Maliyet Etkisi</th>
                  </tr>
                </thead>
                <tbody className="divide-y text-sm">
                  {variance.details.map((item, index) => (
                    <tr key={index} className="hover:bg-gray-50">
                      <td className="p-3 font-medium text-gray-900">{item.name}</td>
                      <td className="p-3 text-gray-500">{item.unit}</td>
                      <td className="p-3 text-right">{item.theoretical}</td>
                      <td className="p-3 text-right">{item.actual}</td>
                      <td className="p-3 text-right">
                        <span className={`px-2 py-1 rounded text-xs font-medium ${item.variance > 0 ? 'bg-red-100 text-red-800' : 'bg-green-100 text-green-800'}`}>
                          {item.variance > 0 ? '+' : ''}{item.variance}
                        </span>
                      </td>
                      <td className={`p-3 text-right font-medium ${item.cost_impact > 0 ? 'text-red-600' : 'text-green-600'}`}>
                        {item.cost_impact > 0 ? '+' : ''}{item.cost_impact?.toLocaleString('tr-TR')} ₺
                      </td>
                    </tr>
                  ))}
                  {(!variance.details || variance.details.length === 0) && (
                    <tr>
                      <td colSpan="6" className="p-6 text-center text-gray-500">Veri bulunamadı.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {activeTab === 1 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {recipes.map(recipe => (
            <div key={recipe.id} className="bg-white border rounded-lg shadow-sm">
              <div className="p-4 border-b flex items-center gap-2 bg-gray-50 rounded-t-lg">
                <FileText className="w-5 h-5 text-indigo-600" />
                <div>
                  <h3 className="font-bold text-gray-900">{recipe.menu_item_name}</h3>
                  <span className="text-xs text-gray-500">Verim: {recipe.yield_portions} Porsiyon</span>
                </div>
              </div>
              <ul className="divide-y p-0 text-sm">
                {recipe.ingredients.map((ing, i) => (
                  <li key={i} className="flex justify-between items-center p-3 hover:bg-gray-50 transition-colors">
                    <span className="text-gray-800">{ing.name}</span>
                    <span className="font-medium text-indigo-700 bg-indigo-50 px-2 py-1 rounded border border-indigo-100">
                      {ing.quantity} {ing.unit}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {/* Confirmation Dialog */}
      {postDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
          <div className="bg-white rounded-lg shadow-lg w-full max-w-md overflow-hidden">
            <div className="p-4 border-b">
              <h3 className="text-lg font-bold">Maliyetleri Muhasebeleştir</h3>
            </div>
            <div className="p-4">
              <p className="mb-4 text-sm text-gray-700">
                Seçili döneme ({variance.start} - {variance.end}) ait gerçekleşen F&B maliyeti 
                <strong> {variance.actual_cost?.toLocaleString('tr-TR')} ₺</strong>.
                Bu tutarı Genel Muhasebe sistemine (Satılan Malın Maliyeti / 740 & 150) aktarmak istiyor musunuz?
              </p>
              <div className="bg-purple-50 border border-purple-200 text-purple-800 p-3 rounded text-sm flex gap-2">
                <AlertCircle className="w-5 h-5 shrink-0" />
                <p>Not: Stok değerlemesi "Gerçekleşen Sayım" baz alınarak fişe işlenecektir.</p>
              </div>
            </div>
            <div className="p-4 border-t flex justify-end gap-2 bg-gray-50">
              <button 
                onClick={() => setPostDialog(false)} 
                disabled={posting}
                className="px-4 py-2 bg-white border rounded hover:bg-gray-100 disabled:opacity-50"
              >
                İptal
              </button>
              <button 
                onClick={handlePostCost} 
                disabled={posting}
                className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50 flex items-center gap-2"
              >
                {posting ? <RefreshCw className="w-4 h-4 animate-spin" /> : 'Muhasebeye Gönder'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
