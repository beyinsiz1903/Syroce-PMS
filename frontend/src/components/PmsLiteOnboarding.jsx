import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function PmsLiteOnboarding({ tenant }) {
  const navigate = useNavigate();

  const tenantId =
    tenant?.id || tenant?._id || tenant?.tenant_id || tenant?.tenantId || "unknown";

  const key = useMemo(
    () => `pms_lite_onboarding_done:${tenantId}`,
    [tenantId]
  );

  const done =
    typeof window !== "undefined" &&
    typeof window.localStorage !== "undefined" &&
    window.localStorage.getItem(key) === "true";

  const [status, setStatus] = useState({ rooms_count: 0, bookings_count: 0 });
  const [loading, setLoading] = useState(true);
  const [step2Done, setStep2Done] = useState(false);

  useEffect(() => {
    const loadStatus = async () => {
      try {
        const res = await axios.get("/pms/setup-status");
        setStatus({
          rooms_count: res.data?.rooms_count ?? 0,
          bookings_count: res.data?.bookings_count ?? 0,
        });
      } catch (e) {
        console.warn("Failed to load PMS setup status", e);
      } finally {
        setLoading(false);
      }
    };

    loadStatus();
  }, []);

  const [step, setStep] = useState(1);

  if (done) return null;

  const finish = () => {
    if (typeof window !== "undefined" && typeof window.localStorage !== "undefined") {
      window.localStorage.setItem(key, "true");
    }
  };

  const steps = [
    {
      n: 1,
      title: "Oda Ekleyin",
      desc: "İlk kurulum için oda(lar)ınızı ekleyin.",
      primary: {
        label: "Hızlı / Çoklu Oda Ekle",
        action: () => {
          const tenantId = tenant?.id || tenant?._id || tenant?.tenant_id || "unknown";
          if (typeof window !== "undefined" && typeof window.localStorage !== "undefined") {
            window.localStorage.setItem(`pms_open_dialog_once:${tenantId}`, "bulk-rooms");
          }
          navigate("/app/pms#rooms");
        },
      },
    },
    {
      n: 2,
      title: "Takvimi Kontrol Edin",
      desc: "Doluluk ve fiyat planınızı takvim üzerinden gözden geçirin.",
      primary: { label: "Takvimi Aç", action: () => navigate("/app/reservation-calendar") },
    },
    {
      n: 3,
      title: "İlk Rezervasyonu Oluşturun",
      desc: "Test amaçlı bir rezervasyon oluşturup sistemi tamamlayın.",
      primary: { label: "Rezervasyonlara Git", action: () => navigate("/app/pms#bookings") },
    },
  ];

  const current = steps.find((s) => s.n === step) || steps[0];

  const roomsDone = status.rooms_count > 0;
  const bookingsDone = status.bookings_count > 0;

  if (!loading && roomsDone && bookingsDone && done) {
    return null;
  }

  return (
    <div className="mb-6">
      <Card className="rounded-2xl">
        <CardHeader>
          <CardTitle>Hızlı Kurulum</CardTitle>
          <CardDescription>
            PMS Lite’ı 2 dakikada kurun — sadece temel adımlar.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <span className="font-medium text-gray-900">Adım {current.n}/3</span>
            <span>•</span>
            <span>{current.title}</span>
          </div>

          <div className="mt-3">
            <div className="text-base font-semibold text-gray-900">{current.title}</div>
            <div className="mt-1 text-sm text-gray-600">{current.desc}</div>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <Button onClick={current.primary.action}>{current.primary.label}</Button>

            {step > 1 && (
              <Button variant="outline" onClick={() => setStep((s) => Math.max(1, s - 1))}>
                Geri
              </Button>
            )}

            {step < 3 ? (
              <Button variant="outline" onClick={() => setStep((s) => Math.min(3, s + 1))}>
                Sonraki
              </Button>
            ) : (
              <Button
                variant="outline"
                onClick={() => {
                  finish();
                  window.location.reload();
                }}
              >
                Kurulumu Bitir
              </Button>
            )}

            <Button
              variant="ghost"
              onClick={() => {
                finish();
                window.location.reload();
              }}
            >
              Şimdilik Atla
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
