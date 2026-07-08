import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import axios from "axios";
import { Calendar, Users, Briefcase } from "lucide-react";
import { format, addDays } from "date-fns";
import { Textarea } from "@/components/ui/textarea";

export default function WebBookingEngine() {
  const { tenantId } = useParams();
  const [searchParams, setSearchParams] = useState({
    check_in: format(new Date(), "yyyy-MM-dd"),
    check_out: format(addDays(new Date(), 1), "yyyy-MM-dd"),
    adults: 1,
    children: 0,
  });
  
  const [rooms, setRooms] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedRoom, setSelectedRoom] = useState(null);
  
  const [guestInfo, setGuestInfo] = useState({
    guest_name: "",
    guest_email: "",
    guest_phone: "",
    special_requests: "",
  });

  const [bookingResult, setBookingResult] = useState(null);

  const handleSearch = async (e) => {
    e.preventDefault();
    setLoading(true);
    setRooms([]);
    setSelectedRoom(null);
    setBookingResult(null);

    try {
      const res = await axios.get(`/wbe/${tenantId}/availability`, { params: searchParams });
      setRooms(res.data);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Müsaitlik sorgulanamadı.");
    } finally {
      setLoading(false);
    }
  };

  const handleBook = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        room_type_id: selectedRoom.room_type_id,
        check_in: searchParams.check_in,
        check_out: searchParams.check_out,
        adults: searchParams.adults,
        children: searchParams.children,
        ...guestInfo
      };
      
      const res = await axios.post(`/wbe/${tenantId}/book`, payload);
      setBookingResult(res.data);
      toast.success("Rezervasyonunuz başarıyla oluşturuldu!");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Rezervasyon oluşturulamadı.");
    } finally {
      setLoading(false);
    }
  };

  if (bookingResult) {
    return (
      <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-4">
        <Card className="w-full max-w-md shadow-xl border-t-4 border-t-indigo-600">
          <CardHeader className="text-center">
            <div className="mx-auto bg-green-100 w-16 h-16 rounded-full flex items-center justify-center mb-4">
              <Calendar className="text-green-600 w-8 h-8" />
            </div>
            <CardTitle className="text-2xl">Rezervasyon Alındı</CardTitle>
            <CardDescription>Bizi tercih ettiğiniz için teşekkür ederiz.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-center">
            <div className="bg-slate-100 p-4 rounded-lg">
              <p className="text-sm text-slate-500 mb-1">Rezervasyon Kodu (PNR)</p>
              <p className="text-xl font-bold font-mono tracking-widest text-indigo-700">
                {bookingResult.confirmation_number}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-4 text-sm mt-4">
              <div className="bg-white border rounded p-2">
                <span className="block text-slate-400 text-xs">Giriş</span>
                <span className="font-semibold">{searchParams.check_in}</span>
              </div>
              <div className="bg-white border rounded p-2">
                <span className="block text-slate-400 text-xs">Çıkış</span>
                <span className="font-semibold">{searchParams.check_out}</span>
              </div>
              <div className="col-span-2 bg-indigo-50 border border-indigo-100 rounded p-2">
                <span className="block text-indigo-400 text-xs">Toplam Tutar</span>
                <span className="font-bold text-indigo-900">{bookingResult.total_price.toLocaleString()} TRY</span>
              </div>
            </div>
            <p className="text-sm text-slate-500 mt-6">
              Rezervasyonunuz <b>Ön Rezervasyon</b> statüsündedir. Otel yetkilileri sizinle en kısa sürede iletişime geçecektir.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-indigo-600 text-white py-6 px-4 shadow-md text-center">
        <h1 className="text-2xl font-bold">Online Rezervasyon</h1>
        <p className="text-indigo-100 mt-1">En iyi fiyat garantisi ile odanızı ayırtın.</p>
      </header>

      <main className="max-w-4xl mx-auto p-4 py-8 space-y-8">
        
        {/* Search Bar */}
        <Card className="shadow-md">
          <CardContent className="p-6">
            <form onSubmit={handleSearch} className="grid grid-cols-1 md:grid-cols-5 gap-4 items-end">
              <div>
                <Label>Check-in</Label>
                <Input 
                  type="date" 
                  value={searchParams.check_in} 
                  onChange={e => setSearchParams({...searchParams, check_in: e.target.value})} 
                  required 
                />
              </div>
              <div>
                <Label>Check-out</Label>
                <Input 
                  type="date" 
                  value={searchParams.check_out} 
                  onChange={e => setSearchParams({...searchParams, check_out: e.target.value})} 
                  required 
                />
              </div>
              <div>
                <Label>Yetişkin</Label>
                <Input 
                  type="number" 
                  min="1" 
                  value={searchParams.adults} 
                  onChange={e => setSearchParams({...searchParams, adults: parseInt(e.target.value)})} 
                  required 
                />
              </div>
              <div>
                <Label>Çocuk</Label>
                <Input 
                  type="number" 
                  min="0" 
                  value={searchParams.children} 
                  onChange={e => setSearchParams({...searchParams, children: parseInt(e.target.value)})} 
                />
              </div>
              <Button type="submit" disabled={loading} className="w-full bg-indigo-600 hover:bg-indigo-700">
                {loading ? "Aranıyor..." : "Müsaitlik Ara"}
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Results */}
        {!selectedRoom && rooms.length > 0 && (
          <div className="space-y-4">
            <h2 className="text-xl font-semibold">Müsait Odalar</h2>
            {rooms.map(room => (
              <Card key={room.room_type_id} className="overflow-hidden hover:shadow-lg transition-shadow">
                <div className="flex flex-col md:flex-row">
                  <div className="md:w-1/3 h-48 md:h-auto bg-slate-200">
                    {room.image_url ? (
                      <img src={room.image_url} alt={room.name} className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-slate-400">
                        <Briefcase className="w-12 h-12 opacity-50" />
                      </div>
                    )}
                  </div>
                  <div className="p-6 flex-1 flex flex-col justify-between">
                    <div>
                      <div className="flex justify-between items-start">
                        <h3 className="text-xl font-bold">{room.name}</h3>
                        <div className="text-right">
                          <span className="text-2xl font-bold text-indigo-600">{room.total_price.toLocaleString()}</span>
                          <span className="text-sm font-medium text-slate-500 ml-1">{room.currency}</span>
                          <div className="text-xs text-slate-400">Toplam Tutar</div>
                        </div>
                      </div>
                      <p className="text-slate-600 mt-2">{room.description}</p>
                      <div className="flex items-center gap-4 mt-4 text-sm text-slate-500">
                        <span className="flex items-center gap-1"><Users className="w-4 h-4"/> Maks: {room.capacity} Kişi</span>
                      </div>
                    </div>
                    <div className="mt-6 flex justify-end">
                      <Button onClick={() => setSelectedRoom(room)} className="bg-indigo-600 hover:bg-indigo-700">
                        Seç ve Devam Et
                      </Button>
                    </div>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}

        {/* Booking Form */}
        {selectedRoom && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="md:col-span-2">
              <Card>
                <CardHeader>
                  <CardTitle>Misafir Bilgileri</CardTitle>
                  <CardDescription>Lütfen iletişim bilgilerinizi eksiksiz doldurun.</CardDescription>
                </CardHeader>
                <CardContent>
                  <form onSubmit={handleBook} className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label>Ad Soyad</Label>
                        <Input 
                          required 
                          value={guestInfo.guest_name} 
                          onChange={e => setGuestInfo({...guestInfo, guest_name: e.target.value})} 
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>E-posta</Label>
                        <Input 
                          type="email" 
                          required 
                          value={guestInfo.guest_email} 
                          onChange={e => setGuestInfo({...guestInfo, guest_email: e.target.value})} 
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Telefon</Label>
                        <Input 
                          type="tel" 
                          required 
                          value={guestInfo.guest_phone} 
                          onChange={e => setGuestInfo({...guestInfo, guest_phone: e.target.value})} 
                        />
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label>Özel İstekleriniz (Opsiyonel)</Label>
                      <Textarea 
                        value={guestInfo.special_requests} 
                        onChange={e => setGuestInfo({...guestInfo, special_requests: e.target.value})} 
                      />
                    </div>
                    <div className="pt-4 flex justify-between">
                      <Button type="button" variant="outline" onClick={() => setSelectedRoom(null)}>
                        Geri Dön
                      </Button>
                      <Button type="submit" disabled={loading} className="bg-indigo-600 hover:bg-indigo-700">
                        {loading ? "İşleniyor..." : "Rezervasyonu Tamamla"}
                      </Button>
                    </div>
                  </form>
                </CardContent>
              </Card>
            </div>
            
            <div>
              <Card className="bg-slate-100 border-none sticky top-4">
                <CardHeader>
                  <CardTitle className="text-lg">Özet</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4 text-sm">
                  <div>
                    <span className="text-slate-500 block mb-1">Oda</span>
                    <strong className="text-base">{selectedRoom.name}</strong>
                  </div>
                  <div className="flex justify-between border-b pb-2">
                    <span className="text-slate-500">Check-in</span>
                    <strong>{searchParams.check_in}</strong>
                  </div>
                  <div className="flex justify-between border-b pb-2">
                    <span className="text-slate-500">Check-out</span>
                    <strong>{searchParams.check_out}</strong>
                  </div>
                  <div className="flex justify-between border-b pb-2">
                    <span className="text-slate-500">Kişi Sayısı</span>
                    <strong>{searchParams.adults} Yetişkin, {searchParams.children} Çocuk</strong>
                  </div>
                  <div className="pt-2 flex justify-between items-end">
                    <span className="text-base font-semibold">Toplam</span>
                    <div className="text-right">
                      <strong className="text-2xl text-indigo-600">{selectedRoom.total_price.toLocaleString()}</strong>
                      <span className="ml-1 text-slate-500">{selectedRoom.currency}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        )}

      </main>
    </div>
  );
}
