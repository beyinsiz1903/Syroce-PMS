import React from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '@/components/Layout';
import { Button } from '@/components/ui/button';
import {
  Package, AlertTriangle, ClipboardList, CheckCircle2, Truck,
  PackageCheck, ArrowRight, ShoppingCart, Sparkles, Lightbulb,
} from 'lucide-react';

const Step = ({ num, icon: Icon, title, desc, color }) => (
  <div className="flex-1 min-w-[180px]">
    <div className={`w-14 h-14 rounded-2xl ${color} text-white flex items-center justify-center shadow-lg mb-3 mx-auto`}>
      <Icon className="w-7 h-7" />
    </div>
    <div className="text-center">
      <div className="text-xs font-bold text-gray-400 mb-1">ADIM {num}</div>
      <h3 className="font-semibold text-gray-900 mb-1">{title}</h3>
      <p className="text-sm text-gray-600 leading-relaxed">{desc}</p>
    </div>
  </div>
);

const Arrow = () => (
  <div className="hidden md:flex items-center text-gray-300 px-2">
    <ArrowRight className="w-6 h-6" />
  </div>
);

const InventoryProcurementGuide = ({ user, tenant, onLogout }) => {
  const navigate = useNavigate();

  const steps = [
    { num: 1, icon: AlertTriangle, title: 'Stok azalır', desc: 'Bir kalem kritik seviyenin altına düşer, sistem uyarı verir.', color: 'bg-orange-500' },
    { num: 2, icon: ClipboardList, title: 'Talep (PR)', desc: 'Departman "Yeni Talep" oluşturur, kalemleri seçer.', color: 'bg-blue-500' },
    { num: 3, icon: CheckCircle2, title: 'Onay', desc: 'Yetkili talebi inceler ve onaylar veya reddeder.', color: 'bg-emerald-500' },
    { num: 4, icon: Truck, title: 'Sipariş (PO)', desc: 'Onaylı talep tedarikçiye sipariş olarak gönderilir.', color: 'bg-indigo-500' },
    { num: 5, icon: PackageCheck, title: 'Mal Kabul', desc: 'Mal geldiğinde kontrol edilir, sisteme girilir.', color: 'bg-purple-500' },
    { num: 6, icon: Package, title: 'Stok Güncel', desc: 'Otel stoğu otomatik artar, döngü tamamlanır.', color: 'bg-pink-500' },
  ];

  return (
    <Layout
      user={user}
      tenant={tenant}
      onLogout={onLogout}
      currentModule="procurement"
      title="Stok ve Satın Alma Rehberi"
      subtitle="Sistem nasıl çalışıyor?"
    >
      <div className="p-6 max-w-6xl mx-auto space-y-8">
        {/* Hero */}
        <div className="bg-gradient-to-br from-blue-600 via-indigo-600 to-purple-700 text-white rounded-3xl p-8 md:p-12 shadow-xl relative overflow-hidden">
          <div className="absolute -top-20 -right-20 w-64 h-64 bg-white/10 rounded-full blur-3xl" />
          <div className="absolute -bottom-20 -left-20 w-64 h-64 bg-white/10 rounded-full blur-3xl" />
          <div className="relative">
            <div className="inline-flex items-center gap-2 px-3 py-1 bg-white/15 rounded-full text-xs font-semibold mb-4">
              <Sparkles className="w-3.5 h-3.5" />
              Hızlı Rehber
            </div>
            <h1 className="text-3xl md:text-4xl font-extrabold mb-3">
              Stoktan siparişe, sipariş bedensiz.
            </h1>
            <p className="text-blue-100 text-base md:text-lg max-w-2xl">
              Tek tuşla stok azalan kaleminizi tedarikçinize sipariş edin.
              Tüm süreç birbirine bağlı, hiçbir adımı atlamadan.
            </p>
            <div className="flex flex-wrap gap-3 mt-6">
              <Button
                onClick={() => navigate('/hotel-inventory')}
                className="bg-white text-blue-700 hover:bg-blue-50 font-semibold"
              >
                <Package className="w-4 h-4 mr-2" /> Stoğa Git
              </Button>
              <Button
                onClick={() => navigate('/app/procurement')}
                variant="outline"
                className="bg-white/10 border-white/30 text-white hover:bg-white/20"
              >
                <ShoppingCart className="w-4 h-4 mr-2" /> Satın Almaya Git
              </Button>
            </div>
          </div>
        </div>

        {/* Flow */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 md:p-10">
          <h2 className="text-xl font-bold text-gray-900 mb-2 text-center">
            6 Adımda Akış
          </h2>
          <p className="text-sm text-gray-600 text-center mb-10">
            İhtiyaçtan teslim alıma kadar her şey takip edilir.
          </p>
          <div className="flex flex-wrap items-start justify-center gap-y-8">
            {steps.map((s, i) => (
              <React.Fragment key={s.num}>
                <Step {...s} />
                {i < steps.length - 1 && <Arrow />}
              </React.Fragment>
            ))}
          </div>
        </div>

        {/* Two-column tips */}
        <div className="grid md:grid-cols-2 gap-6">
          <div className="bg-gradient-to-br from-emerald-50 to-teal-50 border border-emerald-100 rounded-2xl p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-emerald-500 text-white flex items-center justify-center">
                <Package className="w-5 h-5" />
              </div>
              <h3 className="font-bold text-gray-900">Stok ekranında neler yapabilirim?</h3>
            </div>
            <ul className="space-y-2 text-sm text-gray-700">
              {[
                'Tüm kalemleri tek bakışta görürsünüz (mevcut, kritik, tükendi).',
                'Kritik seviyedeki kalemler için "Talep Oluştur" butonu ile tek tıkla satın alma başlatırsınız.',
                'Toplam stok değerini ve düşük stok sayısını anlık takip edersiniz.',
                'Uyarılar sekmesinden hangi kaleme acil sipariş gerektiğini görürsünüz.',
              ].map((t, i) => (
                <li key={i} className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
                  <span>{t}</span>
                </li>
              ))}
            </ul>
            <Button
              onClick={() => navigate('/hotel-inventory')}
              variant="outline"
              className="mt-5 border-emerald-300 text-emerald-700 hover:bg-emerald-100"
              size="sm"
            >
              Stok Ekranına Git <ArrowRight className="w-4 h-4 ml-1" />
            </Button>
          </div>

          <div className="bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-100 rounded-2xl p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-blue-500 text-white flex items-center justify-center">
                <Truck className="w-5 h-5" />
              </div>
              <h3 className="font-bold text-gray-900">Satın alma ekranında neler yapabilirim?</h3>
            </div>
            <ul className="space-y-2 text-sm text-gray-700">
              {[
                'Yeni Talep oluştururken stoktaki kalemlerden listeden seçim yaparsınız.',
                'Onaylı talepleri tek tıkla siparişe dönüştürürsünüz.',
                'Tedarikçinize gönderdiğiniz siparişlerin durumunu (gönderildi, kısmi alındı, tamamlandı) görürsünüz.',
                'Mal geldiğinde "Mal Kabul" ile stoğa otomatik aktarırsınız.',
              ].map((t, i) => (
                <li key={i} className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-blue-600 mt-0.5 shrink-0" />
                  <span>{t}</span>
                </li>
              ))}
            </ul>
            <Button
              onClick={() => navigate('/app/procurement')}
              variant="outline"
              className="mt-5 border-blue-300 text-blue-700 hover:bg-blue-100"
              size="sm"
            >
              Satın Almaya Git <ArrowRight className="w-4 h-4 ml-1" />
            </Button>
          </div>
        </div>

        {/* Tip */}
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5 flex gap-4 items-start">
          <div className="shrink-0 w-10 h-10 rounded-xl bg-amber-400 text-amber-900 flex items-center justify-center">
            <Lightbulb className="w-5 h-5" />
          </div>
          <div>
            <p className="font-semibold text-amber-900 mb-1">İpucu</p>
            <p className="text-sm text-amber-800 leading-relaxed">
              Stok ekranındaki <strong>"Talep Oluştur"</strong> butonuna basarsanız,
              ilgili kalem otomatik olarak satın alma talebine aktarılır. Tekrar
              ad-soyad-birim girmeniz gerekmez. Bu sayede sürekli kullandığınız
              kalemler için saniyeler içinde sipariş başlatabilirsiniz.
            </p>
          </div>
        </div>
      </div>
    </Layout>
  );
};

export default InventoryProcurementGuide;
