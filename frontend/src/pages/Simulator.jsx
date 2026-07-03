import React from 'react';
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Play } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useSimulation } from "@/context/SimulationContext";

export default function Simulator() {
  const navigate = useNavigate();
  const { startSimulation } = useSimulation();

  const scenarios = [
    {
      id: "fd-1",
      department: "Ön Büro",
      title: "VIP Misafir Girişi",
      description: "Ahmet Yılmaz adına VIP bir rezervasyon oluşturun ve check-in işlemlerini tamamlayın.",
      startPath: "/app/reservations",
      totalSteps: 2,
      tasks: [
        {
          instruction: "Rezervasyonlar sayfasından yeni bir kayıt oluşturarak misafir adını 'Ahmet Yılmaz' yapın ve kaydedin.",
          expected_url: "/api/reservations",
          expected_data: {
             guest_name: "Ahmet Yılmaz"
          }
        },
        {
          instruction: "Oluşturduğunuz rezervasyonun detayına gidip Check-in işlemini gerçekleştirin.",
          expected_url: "/checkin", // Backend URL'si neyse (örneğin /api/reservations/.../checkin)
          expected_data: {} // Veri önemli değil, URL eşleşmesi yeterli
        }
      ]
    },
    {
      id: "hk-1",
      department: "Kat Hizmetleri",
      title: "Oda Arıza ve Temizlik Bildirimi",
      description: "Kat görevlisi olarak 105 numaralı odada temizlik yaparken bir arıza tespit ettiniz.",
      startPath: "/app/housekeeping",
      totalSteps: 2,
      tasks: [
        {
          instruction: "Housekeeping tablosundan 105 numaralı odanın durumunu 'Kirli' olarak güncelleyin.",
          expected_url: "/api/rooms/status",
          expected_data: {
             room_id: "105",
             status: "dirty"
          }
        },
        {
          instruction: "Aynı oda için Teknik Servis'e bir arıza talebi (İş Emri) oluşturun.",
          expected_url: "/api/work-orders",
          expected_data: {
             room_id: "105",
             department: "maintenance"
          }
        }
      ]
    },
    {
      id: "fb-1",
      department: "Yiyecek İçecek",
      title: "Oda Servisi Siparişi",
      description: "201 numaralı odadan gelen siparişi sisteme girin ve adisyona yansıtın.",
      startPath: "/app/pos", // Örnek POS/FNB sayfası
      totalSteps: 1,
      tasks: [
        {
          instruction: "Yeni bir adisyon oluşturup 201 numaralı odaya 'Hamburger' ekleyin.",
          expected_url: "/api/pos/tickets",
          expected_data: {
             room_number: "201",
             item: "Hamburger"
          }
        }
      ]
    }
  ];

  const groupedScenarios = scenarios.reduce((acc, curr) => {
    if (!acc[curr.department]) acc[curr.department] = [];
    acc[curr.department].push(curr);
    return acc;
  }, {});

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-center gap-4 mb-8">
        <Button variant="outline" onClick={() => navigate("/app/academy")}>
          <ArrowLeft className="w-4 h-4 mr-2" /> Akademiye Dön
        </Button>
        <div>
           <h1 className="text-2xl font-bold text-slate-900">App-Wide İnteraktif Simülatör</h1>
           <p className="text-slate-500 text-sm">Buradan başlattığınız görevler, otelin gerçek arayüzünde (Sandbox modunda) çözülecektir.</p>
        </div>
      </div>
      
      <div className="space-y-10">
        {Object.entries(groupedScenarios).map(([dept, scens]) => (
          <div key={dept}>
            <h2 className="text-xl font-extrabold text-slate-800 mb-4 pb-2 border-b border-slate-200 uppercase tracking-wider">{dept} Senaryoları</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {scens.map(s => (
                <Card key={s.id} className="p-6 border-slate-200 shadow-sm hover:shadow-md transition-all flex flex-col justify-between">
                  <div>
                    <h3 className="font-bold text-lg mb-2 text-indigo-900">{s.title}</h3>
                    <p className="text-slate-600 text-sm mb-6">{s.description}</p>
                  </div>
                  <Button onClick={() => startSimulation(s)} className="w-full bg-indigo-600 hover:bg-indigo-700">
                    <Play className="w-4 h-4 mr-2" /> Senaryoyu Başlat
                  </Button>
                </Card>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
