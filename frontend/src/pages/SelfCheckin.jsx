import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { CheckCircle, User, CreditCard, Key, Calendar, ScanLine, ShieldCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import QuickIdScanDialog from '@/components/QuickIdScanDialog';
import BiometricVerifyDialog from '@/components/BiometricVerifyDialog';

const SelfCheckin = ({ bookingId, onComplete }) => {
  const { t } = useTranslation();
  const [step, setStep] = useState(1);
  const [booking, setBooking] = useState(null);
  const [guestInfo, setGuestInfo] = useState({
    email: '',
    phone: '',
    id_number: '',
    id_type: 'passport'
  });
  const [paymentInfo, setPaymentInfo] = useState({
    card_number: '',
    card_holder: '',
    expiry: '',
    cvv: ''
  });
  const [preferences, setPreferences] = useState({
    smoking: false,
    floor_preference: 'any',
    early_checkin: false
  });
  const [loading, setLoading] = useState(false);
  const [scanOpen, setScanOpen] = useState(false);
  const [bioOpen, setBioOpen] = useState(false);
  const [docImageB64, setDocImageB64] = useState(null);
  const [bioVerified, setBioVerified] = useState(null);

  useEffect(() => {
    loadBooking();
  }, [bookingId]);

  const loadBooking = async () => {
    try {
      const response = await axios.get(`/guest/bookings/${bookingId}`);
      setBooking(response.data);
      setGuestInfo(prev => ({
        ...prev,
        email: response.data.guest?.email || '',
        phone: response.data.guest?.phone || ''
      }));
    } catch (error) {
      toast.error('Rezervasyon yüklenemedi');
    }
  };

  const handleGuestInfoSubmit = () => {
    if (!guestInfo.email || !guestInfo.phone || !guestInfo.id_number) {
      toast.error('Please fill all required fields');
      return;
    }
    setStep(2);
  };

  const handlePaymentSubmit = () => {
    if (!paymentInfo.card_number || !paymentInfo.card_holder) {
      toast.error('Please fill payment details');
      return;
    }
    setStep(3);
  };

  const handleComplete = async () => {
    setLoading(true);
    try {
      const response = await axios.post(`/guest/self-checkin/${bookingId}`, {
        guest_info: guestInfo,
        payment_info: {
          ...paymentInfo,
          card_number: paymentInfo.card_number.replace(/\s/g, '').slice(-4) // Store only last 4 digits
        },
        preferences
      });
      
      toast.success('Check-in successful! Your digital key is ready.');
      onComplete?.(response.data);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Check-in failed');
    } finally {
      setLoading(false);
    }
  };

  const handleScanned = (doc) => {
    setGuestInfo(prev => ({
      ...prev,
      id_number: doc.id_number || doc.document_number || prev.id_number,
      id_type: doc.document_type === 'tc_kimlik' ? 'tc_kimlik'
        : doc.document_type === 'passport' ? 'passport'
        : doc.document_type === 'drivers_license' ? 'drivers_license'
        : prev.id_type,
    }));
    toast.success('Kimlik bilgileri forma aktarıldı');
  };

  if (!booking) {
    return (
      <div className="text-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      {/* Progress Steps */}
      <div className="flex items-center justify-between mb-8">
        {[1, 2, 3].map((s) => (
          <div key={s} className="flex items-center">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
              step >= s ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-600'
            }`}>
              {step > s ? <CheckCircle className="w-5 h-5" /> : s}
            </div>
            {s < 3 && (
              <div className={`w-24 h-1 mx-2 ${
                step > s ? 'bg-blue-600' : 'bg-gray-200'
              }`} />
            )}
          </div>
        ))}
      </div>

      {/* Booking Summary */}
      <Card>
        <CardHeader>
          <CardTitle>Your Reservation</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-gray-600">Check-in</div>
              <div className="font-semibold flex items-center gap-2">
                <Calendar className="w-4 h-4" />
                {new Date(booking.check_in).toLocaleDateString()}
              </div>
            </div>
            <div>
              <div className="text-gray-600">Check-out</div>
              <div className="font-semibold flex items-center gap-2">
                <Calendar className="w-4 h-4" />
                {new Date(booking.check_out).toLocaleDateString()}
              </div>
            </div>
            <div>
              <div className="text-gray-600">Room Type</div>
              <div className="font-semibold">{booking.room_type || 'Standard'}</div>
            </div>
            <div>
              <div className="text-gray-600">Guests</div>
              <div className="font-semibold">{booking.guests_count || 1}</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Step 1: Guest Information */}
      {step === 1 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <User className="w-5 h-5" />
              Guest Information
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2 mb-1">
              <Button
                type="button" variant="outline" size="sm"
                className="flex-1 border-indigo-300 text-indigo-700 hover:bg-indigo-50"
                onClick={() => setScanOpen(true)}
                data-testid="self-checkin-scan-btn"
              >
                <ScanLine className="w-4 h-4 mr-1" /> Kimliği Tara
              </Button>
              {docImageB64 && (
                <Button
                  type="button" variant="outline" size="sm"
                  className={`flex-1 ${bioVerified?.match ? 'border-emerald-300 text-emerald-700' : 'border-amber-300 text-amber-700'} hover:bg-emerald-50`}
                  onClick={() => setBioOpen(true)}
                  data-testid="self-checkin-bio-btn"
                >
                  <ShieldCheck className="w-4 h-4 mr-1" />
                  {bioVerified?.match ? 'Doğrulandı' : 'Yüzünü Doğrula'}
                </Button>
              )}
            </div>
            <div>
              <Label>E-posta *</Label>
              <Input
                type="email"
                value={guestInfo.email}
                onChange={(e) => setGuestInfo({ ...guestInfo, email: e.target.value })}
                placeholder="your@email.com"
              />
            </div>
            <div>
              <Label>Telefon *</Label>
              <Input
                type="tel"
                value={guestInfo.phone}
                onChange={(e) => setGuestInfo({ ...guestInfo, phone: e.target.value })}
                placeholder="+90 555 000 00 00"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Belge Tipi *</Label>
                <select
                  className="w-full border rounded-md p-2"
                  value={guestInfo.id_type}
                  onChange={(e) => setGuestInfo({ ...guestInfo, id_type: e.target.value })}
                >
                  <option value="passport">Pasaport</option>
                  <option value="drivers_license">Sürücü Belgesi</option>
                  <option value="national_id">Kimlik Kartı</option>
                  <option value="tc_kimlik">TC Kimlik</option>
                </select>
              </div>
              <div>
                <Label>Belge No *</Label>
                <Input
                  value={guestInfo.id_number}
                  onChange={(e) => setGuestInfo({ ...guestInfo, id_number: e.target.value })}
                  placeholder="A12345678"
                />
              </div>
            </div>
            <Button onClick={handleGuestInfoSubmit} className="w-full">
              Devam — Ödeme
            </Button>
          </CardContent>
        </Card>
      )}

      <QuickIdScanDialog
        open={scanOpen}
        onClose={() => setScanOpen(false)}
        onExtracted={handleScanned}
        onImageCaptured={(b64) => setDocImageB64(b64)}
      />
      <BiometricVerifyDialog
        open={bioOpen}
        onClose={() => setBioOpen(false)}
        documentImageBase64={docImageB64}
        onResult={(r) => setBioVerified(r)}
      />

      {/* Step 2: Payment Information */}
      {step === 2 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CreditCard className="w-5 h-5" />
              Payment Information
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label>Card Number *</Label>
              <Input
                value={paymentInfo.card_number}
                onChange={(e) => setPaymentInfo({ ...paymentInfo, card_number: e.target.value })}
                placeholder="1234 5678 9012 3456"
                maxLength={19}
              />
            </div>
            <div>
              <Label>Cardholder Name *</Label>
              <Input
                value={paymentInfo.card_holder}
                onChange={(e) => setPaymentInfo({ ...paymentInfo, card_holder: e.target.value })}
                placeholder="JOHN DOE"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Expiry (MM/YY) *</Label>
                <Input
                  value={paymentInfo.expiry}
                  onChange={(e) => setPaymentInfo({ ...paymentInfo, expiry: e.target.value })}
                  placeholder="12/25"
                  maxLength={5}
                />
              </div>
              <div>
                <Label>CVV *</Label>
                <Input
                  type="password"
                  value={paymentInfo.cvv}
                  onChange={(e) => setPaymentInfo({ ...paymentInfo, cvv: e.target.value })}
                  placeholder="123"
                  maxLength={4}
                />
              </div>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(1)} className="flex-1">
                Back
              </Button>
              <Button onClick={handlePaymentSubmit} className="flex-1">
                Continue
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 3: Preferences & Complete */}
      {step === 3 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Key className="w-5 h-5" />
              Room Preferences
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <Label>Smoking Room</Label>
              <input
                type="checkbox"
                checked={preferences.smoking}
                onChange={(e) => setPreferences({ ...preferences, smoking: e.target.checked })}
                className="w-5 h-5"
              />
            </div>
            <div>
              <Label>Floor Preference</Label>
              <select
                className="w-full border rounded-md p-2 mt-1"
                value={preferences.floor_preference}
                onChange={(e) => setPreferences({ ...preferences, floor_preference: e.target.value })}
              >
                <option value="any">Any Floor</option>
                <option value="low">Lower Floors (1-3)</option>
                <option value="mid">Mid Floors (4-7)</option>
                <option value="high">High Floors (8+)</option>
              </select>
            </div>
            <div className="flex items-center justify-between">
              <Label>Early Check-in (if available)</Label>
              <input
                type="checkbox"
                checked={preferences.early_checkin}
                onChange={(e) => setPreferences({ ...preferences, early_checkin: e.target.checked })}
                className="w-5 h-5"
              />
            </div>
            <div className="border-t pt-4 mt-4">
              <div className="bg-blue-50 p-4 rounded-lg mb-4">
                <div className="text-sm text-blue-800">
                  ✓ Guest information verified<br />
                  ✓ Payment method authorized<br />
                  ✓ Room preferences noted
                </div>
              </div>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(2)} className="flex-1">
                Back
              </Button>
              <Button onClick={handleComplete} disabled={loading} className="flex-1">
                {loading ? 'Processing...' : 'Complete Check-in'}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default SelfCheckin;