import { useState, useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import axios from "axios";
import { Calendar, Users, Briefcase, Wifi, Coffee, Wind, BedDouble, CheckCircle, ArrowRight } from "lucide-react";
import { format, addDays } from "date-fns";
import { Textarea } from "@/components/ui/textarea";

const FEATURED_ROOMS = [
  {
    id: "rt_std_01",
    name: "Standart Oda",
    description: "Şehir manzaralı konforlu standart oda. Modern tasarımı ve rahat yatağı ile günün yorgunluğunu atın.",
    image_url: "/wbe/standard_room.jpg",
    features: ["Ücretsiz Wi-Fi", "Klima", "Mini Bar", "2 Kişilik"],
  },
  {
    id: "rt_dlx_02",
    name: "Deluxe Oda",
    description: "Geniş yaşam alanı ve eşsiz deniz manzarası. Özel balkonunuzda kahvenizi yudumlarken lüksün tadını çıkarın.",
    image_url: "/wbe/deluxe_room.jpg",
    features: ["Deniz Manzarası", "Kral Yatak", "Jakuzi", "3 Kişilik"],
  },
  {
    id: "rt_fam_03",
    name: "Aile Süiti",
    description: "Çocuklu aileler için tasarlanmış geniş süit. İki yatak odası ve ferah oturma alanıyla ev konforu sunar.",
    image_url: "/wbe/family_suite.jpg",
    features: ["İki Yatak Odası", "Mutfak Nişi", "2 Banyo", "5 Kişilik"],
  },
];

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
  const [hasSearched, setHasSearched] = useState(false);
  const resultsRef = useRef(null);
  
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
    setHasSearched(true);
    setRooms([]);
    setSelectedRoom(null);
    setBookingResult(null);

    try {
      const res = await axios.get(`/wbe/${tenantId}/availability`, { params: searchParams });
      setRooms(res.data);
      // Scroll down gently to results
      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: 'smooth' });
      }, 100);
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
      window.scrollTo(0, 0);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Rezervasyon oluşturulamadı.");
    } finally {
      setLoading(false);
    }
  };

  if (bookingResult) {
    return (
      <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-4" style={{
        backgroundImage: "url('/landing/hero-hotel-1280.webp')",
        backgroundSize: "cover",
        backgroundPosition: "center",
      }}>
        <div className="absolute inset-0 bg-black/40 backdrop-blur-sm"></div>
        <Card className="w-full max-w-md shadow-2xl border-none z-10 bg-white/95 backdrop-blur">
          <CardHeader className="text-center pb-2">
            <div className="mx-auto bg-green-500 w-20 h-20 rounded-full flex items-center justify-center mb-6 shadow-lg shadow-green-500/30">
              <CheckCircle className="text-white w-10 h-10" />
            </div>
            <CardTitle className="text-3xl font-light text-slate-800">Rezervasyon Alındı</CardTitle>
            <CardDescription className="text-base mt-2">Bizi tercih ettiğiniz için teşekkür ederiz.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6 text-center">
            <div className="bg-indigo-50/50 p-6 rounded-xl border border-indigo-100">
              <p className="text-sm text-indigo-400 font-medium mb-2 uppercase tracking-wider">Rezervasyon Kodu (PNR)</p>
              <p className="text-3xl font-bold font-mono tracking-widest text-indigo-700">
                {bookingResult.confirmation_number}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-4 text-sm mt-4">
              <div className="bg-slate-50 border rounded-lg p-3 text-left">
                <span className="block text-slate-400 text-xs uppercase tracking-wider mb-1">Giriş</span>
                <span className="font-semibold text-slate-700">{searchParams.check_in}</span>
              </div>
              <div className="bg-slate-50 border rounded-lg p-3 text-left">
                <span className="block text-slate-400 text-xs uppercase tracking-wider mb-1">Çıkış</span>
                <span className="font-semibold text-slate-700">{searchParams.check_out}</span>
              </div>
              <div className="col-span-2 bg-slate-800 text-white rounded-lg p-4 flex justify-between items-center shadow-md">
                <span className="text-sm font-medium text-slate-300">Toplam Tutar</span>
                <span className="text-xl font-bold">{bookingResult.total_price.toLocaleString()} TRY</span>
              </div>
            </div>
            <p className="text-sm text-slate-500 mt-6 px-4">
              Rezervasyonunuz <b>Ön Rezervasyon</b> statüsündedir. Otel yetkilileri sizinle en kısa sürede iletişime geçecektir.
            </p>
            <Button variant="outline" className="mt-4 w-full" onClick={() => window.location.reload()}>
              Yeni Bir Arama Yap
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 font-sans">
      {/* Hero Section */}
      <div className="relative h-[60vh] min-h-[500px] flex items-center justify-center">
        <div 
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: "url('/landing/hero-hotel-1280.webp')" }}
        />
        <div className="absolute inset-0 bg-black/50" />
        <div className="relative z-10 text-center text-white px-4">
          <h1 className="text-4xl md:text-6xl font-light mb-4 tracking-tight drop-shadow-md">Sıradışı Bir Konaklama</h1>
          <p className="text-lg md:text-xl text-slate-200 font-light max-w-2xl mx-auto drop-shadow">
            En iyi fiyat garantisi ve ayrıcalıklı hizmetlerle unutulmaz bir tatil deneyimi için yerinizi hemen ayırtın.
          </p>
        </div>
      </div>

      <main className="max-w-6xl mx-auto px-4 relative z-20 -mt-16 pb-20 space-y-16">
        
        {/* Floating Search Bar */}
        <Card className="shadow-2xl border-none rounded-2xl overflow-hidden bg-white/95 backdrop-blur-md">
          <CardContent className="p-2 md:p-4">
            <form onSubmit={handleSearch} className="flex flex-col md:flex-row gap-4 items-end">
              <div className="flex-1 w-full px-4 pt-2">
                <Label className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-2 block">Giriş Tarihi</Label>
                <Input 
                  type="date" 
                  value={searchParams.check_in} 
                  onChange={e => setSearchParams({...searchParams, check_in: e.target.value})} 
                  required 
                  className="border-none shadow-none text-lg p-0 h-auto focus-visible:ring-0 cursor-pointer"
                />
              </div>
              <div className="hidden md:block w-px h-12 bg-slate-200"></div>
              <div className="flex-1 w-full px-4 pt-2">
                <Label className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-2 block">Çıkış Tarihi</Label>
                <Input 
                  type="date" 
                  value={searchParams.check_out} 
                  onChange={e => setSearchParams({...searchParams, check_out: e.target.value})} 
                  required 
                  className="border-none shadow-none text-lg p-0 h-auto focus-visible:ring-0 cursor-pointer"
                />
              </div>
              <div className="hidden md:block w-px h-12 bg-slate-200"></div>
              <div className="flex-1 w-full px-4 pt-2">
                <Label className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-2 block">Yetişkin</Label>
                <Input 
                  type="number" 
                  min="1" 
                  value={searchParams.adults} 
                  onChange={e => setSearchParams({...searchParams, adults: parseInt(e.target.value)})} 
                  required 
                  className="border-none shadow-none text-lg p-0 h-auto focus-visible:ring-0"
                />
              </div>
              <div className="hidden md:block w-px h-12 bg-slate-200"></div>
              <div className="flex-1 w-full px-4 pt-2">
                <Label className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-2 block">Çocuk</Label>
                <Input 
                  type="number" 
                  min="0" 
                  value={searchParams.children} 
                  onChange={e => setSearchParams({...searchParams, children: parseInt(e.target.value)})} 
                  className="border-none shadow-none text-lg p-0 h-auto focus-visible:ring-0"
                />
              </div>
              <div className="w-full md:w-auto p-2">
                <Button type="submit" disabled={loading} size="lg" className="w-full h-14 px-8 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-lg font-medium transition-all shadow-lg hover:shadow-xl">
                  {loading ? "Aranıyor..." : "Müsaitlik Ara"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        {/* Dynamic Content Area (Results OR Featured Rooms) */}
        <div ref={resultsRef} className="scroll-mt-8">
          
          {/* Featured Rooms (Show when not searched or when searching but no results yet and haven't selected a room) */}
          {!hasSearched && !selectedRoom && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700 pt-8">
              <div className="text-center space-y-2">
                <h2 className="text-3xl font-light text-slate-800">Odalarımız ve Süitlerimiz</h2>
                <p className="text-slate-500 max-w-2xl mx-auto">Her detayı özenle düşünülmüş, lüks ve konforu bir arada sunan odalarımızda kendinizi özel hissedeceksiniz.</p>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                {FEATURED_ROOMS.map((room) => (
                  <Card key={room.id} className="overflow-hidden border-none shadow-lg hover:shadow-xl transition-all duration-300 group cursor-pointer bg-white">
                    <div className="relative h-64 overflow-hidden">
                      <img src={room.image_url} alt={room.name} className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105" />
                      <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent"></div>
                      <div className="absolute bottom-4 left-4 right-4 text-white">
                        <h3 className="text-2xl font-medium">{room.name}</h3>
                      </div>
                    </div>
                    <CardContent className="p-6">
                      <p className="text-slate-600 text-sm line-clamp-3 mb-4">{room.description}</p>
                      <div className="flex flex-wrap gap-2">
                        {room.features.map((feature, i) => (
                          <span key={i} className="px-2 py-1 bg-slate-100 text-slate-600 text-xs rounded-md font-medium">
                            {feature}
                          </span>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {/* Search Results */}
          {hasSearched && !selectedRoom && rooms.length > 0 && (
            <div className="space-y-6 animate-in fade-in duration-500">
              <div className="flex items-center justify-between border-b pb-4">
                <h2 className="text-2xl font-light text-slate-800">Müsait Odalar</h2>
                <span className="text-slate-500 bg-slate-100 px-3 py-1 rounded-full text-sm font-medium">{rooms.length} oda bulundu</span>
              </div>
              
              <div className="space-y-6">
                {rooms.map(room => (
                  <Card key={room.room_type_id} className="overflow-hidden border-none shadow-md hover:shadow-lg transition-all bg-white group">
                    <div className="flex flex-col md:flex-row">
                      <div className="md:w-[350px] h-64 md:h-auto relative overflow-hidden">
                        {room.image_url ? (
                          <img src={room.image_url} alt={room.name} className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105" />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center bg-slate-100">
                            <BedDouble className="w-12 h-12 text-slate-300" />
                          </div>
                        )}
                      </div>
                      <div className="p-6 flex-1 flex flex-col">
                        <div className="flex justify-between items-start gap-4">
                          <div>
                            <h3 className="text-2xl font-medium text-slate-800">{room.name}</h3>
                            <div className="flex items-center gap-4 mt-3 text-sm text-slate-600">
                              <span className="flex items-center gap-1.5"><Users className="w-4 h-4 text-slate-400"/> Maks {room.capacity} Kişi</span>
                              <span className="flex items-center gap-1.5"><Wifi className="w-4 h-4 text-slate-400"/> Ücretsiz Wi-Fi</span>
                              <span className="flex items-center gap-1.5"><Coffee className="w-4 h-4 text-slate-400"/> Kahvaltı Dahil</span>
                            </div>
                          </div>
                          <div className="text-right bg-slate-50 p-4 rounded-xl border border-slate-100">
                            <div className="text-sm text-slate-500 mb-1">Toplam Konaklama</div>
                            <div className="flex items-baseline justify-end gap-1">
                              <span className="text-3xl font-bold text-slate-900">{room.total_price.toLocaleString()}</span>
                              <span className="text-lg font-medium text-slate-600">{room.currency}</span>
                            </div>
                            <div className="text-xs text-slate-400 mt-1">Vergiler ve harçlar dahildir</div>
                          </div>
                        </div>
                        <p className="text-slate-600 mt-4 leading-relaxed line-clamp-2">{room.description}</p>
                        
                        <div className="mt-auto pt-6 flex justify-end">
                          <Button 
                            onClick={() => {
                              setSelectedRoom(room);
                              window.scrollTo({ top: 0, behavior: 'smooth' });
                            }} 
                            size="lg"
                            className="bg-slate-900 hover:bg-slate-800 text-white px-8 rounded-lg"
                          >
                            Hemen Ayırt <ArrowRight className="w-4 h-4 ml-2" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {/* No Results Empty State */}
          {hasSearched && !selectedRoom && rooms.length === 0 && !loading && (
            <div className="text-center py-20 bg-white rounded-2xl shadow-sm border border-slate-100 mt-8">
              <div className="bg-slate-100 w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-6">
                <Calendar className="w-10 h-10 text-slate-400" />
              </div>
              <h3 className="text-2xl font-medium text-slate-800 mb-2">Seçili Tarihlerde Müsait Oda Bulunamadı</h3>
              <p className="text-slate-500 max-w-md mx-auto">
                Lütfen farklı tarihler seçerek veya misafir sayısını değiştirerek tekrar arama yapınız.
              </p>
            </div>
          )}

          {/* Booking Form */}
          {selectedRoom && (
            <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 pt-4">
              <div className="mb-6 flex items-center gap-2 text-sm">
                <button onClick={() => setSelectedRoom(null)} className="text-slate-500 hover:text-slate-900 transition-colors">Arama Sonuçları</button>
                <span className="text-slate-300">/</span>
                <span className="font-medium text-slate-900">Misafir Bilgileri</span>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div className="lg:col-span-2 space-y-6">
                  
                  {/* Selected Room Summary (Mobile only, hidden on desktop as it's in sidebar) */}
                  <Card className="lg:hidden bg-slate-50 border-none shadow-sm">
                    <CardContent className="p-6">
                      <h3 className="font-medium text-lg mb-2">{selectedRoom.name}</h3>
                      <div className="flex justify-between items-end">
                        <div className="text-sm text-slate-600">
                          {searchParams.check_in} - {searchParams.check_out} <br/>
                          {searchParams.adults} Yetişkin, {searchParams.children} Çocuk
                        </div>
                        <div className="font-bold text-xl">{selectedRoom.total_price.toLocaleString()} {selectedRoom.currency}</div>
                      </div>
                    </CardContent>
                  </Card>

                  <Card className="border-none shadow-lg bg-white overflow-hidden rounded-2xl">
                    <div className="bg-slate-900 text-white p-6">
                      <h2 className="text-xl font-medium">Misafir Bilgileri</h2>
                      <p className="text-slate-300 text-sm mt-1">Lütfen rezervasyonu tamamlamak için bilgilerinizi giriniz.</p>
                    </div>
                    <CardContent className="p-8">
                      <form onSubmit={handleBook} className="space-y-6">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                          <div className="space-y-2">
                            <Label className="text-slate-700">Ad Soyad <span className="text-red-500">*</span></Label>
                            <Input 
                              required 
                              className="bg-slate-50 border-slate-200 focus:bg-white transition-colors h-12"
                              placeholder="Örn: Ahmet Yılmaz"
                              value={guestInfo.guest_name} 
                              onChange={e => setGuestInfo({...guestInfo, guest_name: e.target.value})} 
                            />
                          </div>
                          <div className="space-y-2">
                            <Label className="text-slate-700">E-posta Adresi <span className="text-red-500">*</span></Label>
                            <Input 
                              type="email" 
                              required 
                              className="bg-slate-50 border-slate-200 focus:bg-white transition-colors h-12"
                              placeholder="Örn: ahmet@example.com"
                              value={guestInfo.guest_email} 
                              onChange={e => setGuestInfo({...guestInfo, guest_email: e.target.value})} 
                            />
                          </div>
                          <div className="space-y-2 md:col-span-2">
                            <Label className="text-slate-700">Cep Telefonu <span className="text-red-500">*</span></Label>
                            <Input 
                              type="tel" 
                              required 
                              className="bg-slate-50 border-slate-200 focus:bg-white transition-colors h-12"
                              placeholder="+90 5XX XXX XX XX"
                              value={guestInfo.guest_phone} 
                              onChange={e => setGuestInfo({...guestInfo, guest_phone: e.target.value})} 
                            />
                          </div>
                        </div>
                        
                        <hr className="border-slate-100" />
                        
                        <div className="space-y-2">
                          <Label className="text-slate-700">Özel İstekleriniz (Opsiyonel)</Label>
                          <Textarea 
                            className="bg-slate-50 border-slate-200 focus:bg-white min-h-[120px] resize-y"
                            placeholder="Erken giriş, alerjen uyarıları, yatak tercihi vb. (İstekler garanti edilmemektedir, otel müsaitliğine göre değerlendirilir.)"
                            value={guestInfo.special_requests} 
                            onChange={e => setGuestInfo({...guestInfo, special_requests: e.target.value})} 
                          />
                        </div>
                        
                        <div className="pt-6">
                          <Button type="submit" disabled={loading} size="lg" className="w-full h-14 text-lg font-medium bg-indigo-600 hover:bg-indigo-700 shadow-lg shadow-indigo-600/20">
                            {loading ? "İşleniyor..." : "Rezervasyonu Onayla"}
                          </Button>
                          <p className="text-center text-xs text-slate-500 mt-4">
                            Bu aşamada ödeme alınmayacaktır. Tesis varışta ödeme kabul etmektedir.
                          </p>
                        </div>
                      </form>
                    </CardContent>
                  </Card>
                </div>
                
                {/* Sidebar Summary (Desktop) */}
                <div className="hidden lg:block">
                  <Card className="border-none shadow-lg bg-white rounded-2xl sticky top-8 overflow-hidden">
                    {selectedRoom.image_url && (
                      <div className="h-48 relative">
                        <img src={selectedRoom.image_url} alt={selectedRoom.name} className="w-full h-full object-cover" />
                        <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent flex items-end p-6">
                          <h3 className="text-white font-medium text-xl">{selectedRoom.name}</h3>
                        </div>
                      </div>
                    )}
                    <CardContent className="p-6 space-y-6">
                      {!selectedRoom.image_url && (
                         <h3 className="font-medium text-xl border-b pb-4">{selectedRoom.name}</h3>
                      )}
                      
                      <div className="space-y-4 text-sm">
                        <div className="flex items-start gap-4">
                          <div className="bg-slate-100 p-3 rounded-lg flex-1">
                            <span className="text-slate-500 text-xs uppercase tracking-wider block mb-1">Giriş</span>
                            <strong className="text-slate-900 text-base">{searchParams.check_in}</strong>
                          </div>
                          <div className="bg-slate-100 p-3 rounded-lg flex-1">
                            <span className="text-slate-500 text-xs uppercase tracking-wider block mb-1">Çıkış</span>
                            <strong className="text-slate-900 text-base">{searchParams.check_out}</strong>
                          </div>
                        </div>
                        
                        <div className="flex justify-between py-2 border-b border-slate-100">
                          <span className="text-slate-600">Konaklama Süresi</span>
                          <strong className="text-slate-900">
                            {(new Date(searchParams.check_out) - new Date(searchParams.check_in)) / (1000 * 60 * 60 * 24)} Gece
                          </strong>
                        </div>
                        <div className="flex justify-between py-2 border-b border-slate-100">
                          <span className="text-slate-600">Misafir</span>
                          <strong className="text-slate-900">{searchParams.adults} Yetişkin{searchParams.children > 0 ? `, ${searchParams.children} Çocuk` : ''}</strong>
                        </div>
                      </div>

                      <div className="pt-2 bg-slate-50 p-4 rounded-xl">
                        <div className="flex justify-between items-center mb-1">
                          <span className="text-slate-600 font-medium">Toplam Tutar</span>
                          <div className="text-right">
                            <strong className="text-2xl text-slate-900">{selectedRoom.total_price.toLocaleString()}</strong>
                            <span className="ml-1 text-slate-600 font-medium">{selectedRoom.currency}</span>
                          </div>
                        </div>
                        <p className="text-xs text-slate-500 text-right">Vergiler ve harçlar dahildir</p>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </div>
            </div>
          )}

        </div>
      </main>

      {/* Simple Footer */}
      <footer className="bg-slate-900 text-slate-400 py-12 text-center text-sm relative z-20">
        <p>&copy; {new Date().getFullYear()} Otel Rezervasyon Sistemi. Tüm hakları saklıdır.</p>
      </footer>
    </div>
  );
}
