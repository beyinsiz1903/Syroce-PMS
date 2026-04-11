# 🏨 RoomOps - Front Desk Eğitim Programı (2-3 Saat)

## 📋 Eğitim İçeriği

**Hedef Kitle:** Resepsiyon görevlileri, Front Office staff
**Süre:** 2-3 saat (2 saat teori + 1 saat pratik)
**Seviye:** Başlangıç

---

## Modül 1: Sisteme Giriş ve Temel Kavramlar (30 dakika)

### 1.1 Login İşlemi

**Adım adım:**

1. **Tarayıcıyı açın**
   - Chrome, Firefox, veya Edge önerilir
   - URL: `https://your-hotel.roomops.com`

2. **Login bilgilerinizi girin**
   ```
   Email: [your-email@hotel.com]
   Password: [********]
   
   [Login]
   ```

3. **İlk giriş - Şifre değiştirme**
   - Sistem sizden yeni şifre isteyecek
   - Güçlü şifre kullanın (min 8 karakter)
   - Şifrenizi kimseyle paylaşmayın

**💡 İpucu:** Şifrenizi unutursanız, supervisor'ünüze veya IT'ye başvurun.

---

### 1.2 Ana Dashboard Tanıtımı

**Dashboard bölümleri:**

```
┌─────────────────────────────────────────────────────────┐
│ 🏨 RoomOps              [Dashboard] [PMS] [Calendar]   │
│                         Sarah Johnson ▼  🌐 EN  🔔     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  📊 Today's Overview                                    │
│  ┌──────────┬──────────┬──────────┬──────────┐        │
│  │ Check-ins│Check-outs│ Arrivals │ Stayovers│        │
│  │    12    │     8    │    15    │    25    │        │
│  └──────────┴──────────┴──────────┴──────────┘        │
│                                                          │
│  🛏️ Room Status                                        │
│  Occupied: 35  Available: 5  Dirty: 8  OOO: 2         │
│                                                          │
│  📅 Quick Actions                                       │
│  [New Booking] [Check-in] [Check-out] [Search]        │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

**Önemli bölümler:**
- **Today's Overview:** Günlük özet
- **Room Status:** Oda durumları
- **Quick Actions:** Hızlı işlemler
- **Notifications (🔔):** Önemli bildirimler

---

### 1.3 Navigasyon Menüsü

**Ana menüler:**

1. **Dashboard (🏠)** - Ana sayfa
2. **PMS (🏨)** - Rezervasyon yönetimi
   - Bookings
   - Rooms
   - Guests
   - Folios
3. **Calendar (📅)** - Rezervasyon takvimi
4. **Reports (📊)** - Raporlar

**💡 İpucu:** PMS modülünde en çok zaman geçireceksiniz.

---

## Modül 2: Rezervasyon İşlemleri (45 dakika)

### 2.1 Yeni Rezervasyon Oluşturma

**Senaryo:** Telefonda arayan misafir için rezervasyon oluşturma

**Adımlar:**

1. **PMS → Bookings → New Booking**

2. **Guest Information (Misafir Bilgileri)**
   ```
   First Name: [John]
   Last Name: [Smith]
   Email: [john.smith@email.com]
   Phone: [+1-555-1234]
   
   Nationality: [USA]
   ID Type: [Passport]
   ID Number: [AB1234567]
   ```

3. **Booking Details (Rezervasyon Detayları)**
   ```
   Check-in Date: [2025-01-20]
   Check-out Date: [2025-01-23]
   Nights: 3 (otomatik hesaplanır)
   
   Room Type: [Deluxe Room]
   Number of Rooms: [1]
   
   Adults: [2]
   Children: [0]
   ```

4. **Rate & Pricing (Fiyat)**
   ```
   Rate Type: [BAR - Best Available Rate]
   Base Rate: [$200.00] per night
   Total Room: $600.00
   
   Taxes (18% VAT): $108.00
   Tourism Tax: $15.00
   
   Total Amount: $723.00
   ```

5. **Special Requests (Özel İstekler)**
   ```
   □ Late check-in
   □ Early check-out
   ☑ High floor preference
   □ Smoking room
   
   Notes:
   [Guest celebrates anniversary. Please add
   a bottle of wine to the room.]
   ```

6. **Payment & Guarantee (Ödeme)**
   ```
   Guarantee Type: [Credit Card]
   
   Card Number: [**** **** **** 1234]
   Expiry: [12/26]
   CVV: [***]
   Cardholder: [John Smith]
   ```

7. **Review & Confirm**
   ```
   Guest: John Smith
   Check-in: Jan 20, 2025
   Check-out: Jan 23, 2025
   Room Type: Deluxe Room
   Total: $723.00
   
   [Confirm Booking] [Cancel]
   ```

8. **Confirmation**
   ```
   ✅ Booking Created Successfully!
   
   Booking ID: BKG-20250115-001
   Confirmation sent to: john.smith@email.com
   
   [View Booking] [Print Confirmation] [Close]
   ```

**⚠️ Dikkat:**
- Tüm zorunlu alanları doldurun (*)
- Email adresini doğru girin (confirmation gönderilecek)
- Credit card bilgilerini dikkatli girin

---

### 2.2 Rezervasyon Arama

**Arama yöntemleri:**

1. **Booking ID ile:**
   ```
   Search: [BKG-20250115-001]
   ```

2. **Guest Name ile:**
   ```
   Search: [John Smith]
   ```

3. **Email ile:**
   ```
   Search: [john.smith@email.com]
   ```

4. **Phone ile:**
   ```
   Search: [+1-555-1234]
   ```

5. **Advanced Filters:**
   ```
   Date Range: [2025-01-15] to [2025-01-20]
   Status: [Confirmed]
   Room Type: [All]
   
   [Search]
   ```

**💡 İpucu:** Arama yaparken en az 3 karakter girin.

---

### 2.3 Rezervasyon Modifikasyonu

**Senaryo:** Misafir bir gece daha kalmak istiyor

**Adımlar:**

1. **Rezervasyonu bulun ve açın**

2. **Edit Booking**

3. **Değişiklikleri yapın**
   ```
   OLD:
   Check-out: Jan 23, 2025
   Nights: 3
   Total: $723.00
   
   NEW:
   Check-out: Jan 24, 2025
   Nights: 4
   Total: $964.00
   ```

4. **Rate recalculation**
   - Sistem otomatik fiyat hesaplayacak
   - Ek gün: $200 + tax

5. **Save Changes**
   ```
   ⚠️ Booking Modification
   
   Changes:
   - Check-out extended: Jan 23 → Jan 24
   - Additional charge: $241.00
   
   Send confirmation email?
   ☑ Yes, send to john.smith@email.com
   
   [Confirm Changes] [Cancel]
   ```

**⚠️ Dikkat:** Önemli değişiklerde (tarih, oda tipi, fiyat) mutlaka guest'i bilgilendirin.

---

### 2.4 Rezervasyon İptali

**Senaryo:** Misafir iptal etmek istiyor

**Adımlar:**

1. **Rezervasyonu açın**

2. **Cancel Booking button**

3. **Cancellation Policy kontrolü**
   ```
   Cancellation Policy: Standard
   
   - Free cancellation: 24 hours before arrival
   - Late cancellation fee: 1 night charge
   - No-show fee: Full amount
   
   Current Status:
   - Days until arrival: 5 days
   - Cancellation fee: $0 (Free cancellation)
   ```

4. **Cancellation reason**
   ```
   Reason: [Guest's plans changed]
   
   Cancellation fee: $0.00
   Refund amount: $723.00
   
   Notes (optional):
   [Guest may rebook for next month]
   ```

5. **Confirm cancellation**
   ```
   ✅ Booking Cancelled
   
   Booking ID: BKG-20250115-001
   Cancellation ID: CXL-20250115-001
   Refund: $723.00 (processed in 5-7 business days)
   
   Cancellation email sent to guest.
   
   [Close]
   ```

**⚠️ Önemli:** 
- Cancellation policy'yi mutlaka kontrol edin
- Guest'e refund süresini bildirin
- Cancellation confirmation print edin

---

## Modül 3: Check-in İşlemleri (30 dakika)

### 3.1 Standart Check-in

**Senaryo:** John Smith check-in için geldi

**Adımlar:**

1. **Reservation lookup**
   ```
   Search: [John Smith] or [BKG-20250115-001]
   ```

2. **Verify guest identity**
   - ID/Passport kontrolü
   - Misafir bilgileri doğrulama
   ```
   Guest: John Smith
   ID: Passport AB1234567
   Phone: +1-555-1234
   
   ✅ Identity verified
   ```

3. **Room assignment**
   ```
   Reserved Room Type: Deluxe Room
   
   Available Rooms:
   □ Room 301 - Deluxe, 3rd Floor, City View
   ☑ Room 405 - Deluxe, 4th Floor, Sea View (High floor - Guest preference)
   □ Room 507 - Deluxe, 5th Floor, Garden View
   
   [Assign Room]
   ```

4. **Create guest folio**
   ```
   ✅ Folio created: F-2025-00123
   
   Initial balance: $723.00 (Room charges)
   Status: Open
   ```

5. **Payment collection (optional)**
   ```
   Collect deposit?
   ☑ Yes
   
   Amount: [$300.00]
   Payment Method: [Credit Card]
   
   [Process Payment]
   ```

6. **Key card programming**
   ```
   Room: 405
   Check-in: Jan 20, 2025 14:00
   Check-out: Jan 23, 2025 12:00
   
   [Program Key Cards] (x2)
   ```

7. **Final confirmation**
   ```
   ✅ Check-in Completed
   
   Guest: John Smith
   Room: 405 (Deluxe Room)
   Checkout: Jan 23, 12:00 PM
   
   WiFi: HotelGuest / Password: Welcome2025
   Breakfast: 7:00 AM - 10:30 AM (Restaurant)
   
   [Print Registration Card] [Close]
   ```

8. **Welcome guest**
   - Key card'ları verin (2 adet)
   - Registration card imzalatın
   - Hotel facilities anlatın
   - "Enjoy your stay!" 😊

**💡 İpucu:** 
- Misafir tercihlerini (high floor, quiet room) her zaman göz önünde bulundurun
- Key card programlarken check-out saatini doğru girin
- Registration card'ı mutlaka imzalatın (legal requirement)

---

### 3.2 Walk-in Guest (Rezervasyonsuz Check-in)

**Senaryo:** Rezervasyonsuz misafir geldi

**Adımlar:**

1. **Room availability check**
   ```
   Dates: Today → +2 nights
   Room Type: Any available
   
   Available Rooms: 5
   - 2 Standard Rooms
   - 2 Deluxe Rooms
   - 1 Suite
   ```

2. **Create booking (hızlı)**
   - Guest information gir
   - Dates seç
   - Room assign et
   - Payment collect et (ön ödeme önemli!)

3. **Immediate check-in**
   - Folio oluştur
   - Key program et
   - Registration card imzalat

**⚠️ Dikkat:** 
- Walk-in guests için mutlaka ön ödeme alın
- Rate walk-in rate (genellikle BAR rate)
- Credit card imprint alın

---

### 3.3 Early Check-in

**Senaryo:** Misafir 10:00'da geldi (check-in time: 14:00)

**Durum 1: Room hazır**
```
Room 405 Status: Clean, Inspected ✅

Early check-in: No charge
[Proceed with Check-in]
```

**Durum 2: Room hazır değil**
```
Room 405 Status: Dirty, Cleaning in progress 🧹

Options:
1. Wait until 14:00 (standard check-in)
2. Assign different available room
3. Store luggage, use facilities

💡 "Your room will be ready by 14:00. May I store
   your luggage? You can use our facilities and
   restaurant meanwhile."
```

**Early check-in fee (opsiyonel):**
```
Early check-in (before 12:00): $50.00

☑ Charge early check-in fee
[Confirm]
```

---

## Modül 4: Check-out İşlemleri (30 dakika)

### 4.1 Standart Check-out

**Senaryo:** John Smith check-out yapıyor

**Adımlar:**

1. **Retrieve guest folio**
   ```
   Search: Room [405] or [John Smith]
   ```

2. **Review folio charges**
   ```
   Folio: F-2025-00123
   Guest: John Smith, Room 405
   
   CHARGES:
   Jan 20 - Room charge       $241.00
   Jan 21 - Room charge       $241.00
   Jan 22 - Room charge       $241.00
   Jan 21 - Minibar           $25.00
   Jan 22 - Room service      $45.00
   
   Subtotal:                  $793.00
   VAT (18%):                 $142.74
   Tourism Tax:               $15.00
   
   Total Charges:             $950.74
   
   PAYMENTS:
   Jan 20 - Deposit (CC)      $300.00
   
   Balance Due:               $650.74
   ```

3. **Ask guest to verify**
   ```
   "Mr. Smith, your total is $650.74. Would you
   like to review the charges?"
   
   [Show detailed folio]
   ```

4. **Collect payment**
   ```
   Balance: $650.74
   
   Payment Method:
   ☑ Credit Card (same card used for deposit)
   □ Cash
   □ Company billing
   
   [Process Payment]
   ```

5. **Payment confirmation**
   ```
   ✅ Payment Successful
   
   Amount charged: $650.74
   Card: **** **** **** 1234
   Transaction ID: TXN-20250123-789
   
   Total paid: $950.74
   ```

6. **Close folio**
   ```
   ✅ Folio closed
   Balance: $0.00
   
   [Print Invoice] [Email Invoice]
   ```

7. **Complete check-out**
   ```
   ✅ Check-out Completed
   
   Guest: John Smith
   Room: 405
   Checkout time: 11:45 AM
   
   Room status updated: Dirty
   Housekeeping notified
   
   [Close]
   ```

8. **Thank guest**
   ```
   "Thank you for staying with us, Mr. Smith!
   We hope to see you again soon!
   Have a safe journey! 😊"
   
   [Print invoice and hand key cards]
   ```

**💡 İpucu:**
- Invoice'ı mutlaka print edin veya email gönderin
- Guest satisfaction survey teklif edin
- Loyalty program'a davet edin

---

### 4.2 Express Check-out

**Senaryo:** Misafir sabah erken ayrılacak, check-out yapmak istemiyor

**Adımlar:**

1. **Night audit sırasında prepare et**
   - Folio'yu finalize et
   - Pre-authorize credit card
   - Express checkout form hazırla

2. **Misafir gece önce:**
   ```
   Express Checkout Form
   
   Room: 405
   Guest: John Smith
   
   ☑ I authorize the hotel to charge my credit
      card on file for all room charges.
   
   Card: **** **** **** 1234
   Estimated total: $650.74
   
   Signature: ________________
   Date: Jan 22, 2025
   ```

3. **Sabah:**
   - Misafir key card'ı bırakır (drop box)
   - Otomatik charge
   - Email ile invoice gönder
   - Check-out complete

**💡 İpucu:** Express checkout business travelers için ideal.

---

### 4.3 Late Check-out

**Senaryo:** Misafir 15:00'a kadar kalmak istiyor (normal check-out: 12:00)

**Durum 1: Room'a same day arrival yok**
```
✅ Late checkout available

Fee: $25.00 (until 15:00)

"No problem, Mr. Smith. You can stay until
3 PM for an additional $25."

[Apply Late Checkout]
```

**Durum 2: Room'a arrival var**
```
❌ Late checkout NOT available

Reason: Room 405 has arrival at 14:00

Options:
1. Luggage storage
2. Day use area

"I'm sorry, your room is booked for today.
We can store your luggage and you can use
our lobby and facilities."
```

**⚠️ Dikkat:** Late checkout için mutlaka room availability kontrol edin.

---

## Modül 5: Günlük Operasyonlar (15 dakika)

### 5.1 Night Audit Hazırlık

**Evening shift tasks (22:00 - 00:00):**

1. **Tomorrow's arrivals review**
   ```
   Tomorrow (Jan 16):
   - Arrivals: 15 bookings
   - VIP: 2 guests
   - Late arrivals: 3 guests (after 22:00)
   - Special requests: 5 guests
   ```

2. **Room blocks check**
   - Pre-assign rooms
   - Check special requests
   - Prepare VIP amenities

3. **Outstanding charges review**
   - Unpaid late charges
   - Minibar consumption
   - Room service orders

4. **Express checkouts prepare**
   - Tomorrow departures
   - Pre-authorize cards
   - Prepare invoices

---

### 5.2 Handover (Vardiya Devir)

**Shift handover checklist:**

```
📋 Shift Handover - Front Desk
Date: Jan 15, 2025
From: Sarah Johnson (Day shift)
To: Mike Davis (Evening shift)

✅ COMPLETED TODAY:
- Check-ins: 12 (all completed)
- Check-outs: 8 (all settled)
- New bookings: 5
- Cancellations: 1

⚠️ PENDING ISSUES:
1. Room 302 - A/C issue reported
   → Engineering notified, repair scheduled

2. VIP arrival tonight (21:30)
   → Mr. James Wilson, Suite 601
   → Welcome amenity prepared
   → Late check-in key ready

3. Outstanding payment
   → Room 205, Mr. Anderson
   → $150 minibar charges
   → Collect at checkout tomorrow

📌 TOMORROW PRIORITIES:
- Heavy check-in day (15 arrivals)
- Group check-in at 14:00 (8 rooms)
- Late departure approval needed (Room 408)

Notes:
[Any additional notes...]

Handover completed: ✅
Signature: _______________
Time: 15:00
```

**💡 İpucu:** Net ve detaylı handover, ekip başarısının temelidir.

---

### 5.3 Günlük Raporlar

**Manager'a günlük report:**

```
📊 Daily Front Desk Report
Date: January 15, 2025

🏨 OCCUPANCY:
- Occupied Rooms: 38/50 (76%)
- Arrivals: 12
- Departures: 8
- Stayovers: 26
- No-shows: 0

💰 REVENUE:
- Room Revenue: $6,450
- Average Rate: $169.74
- RevPAR: $129.00

📝 OPERATIONS:
- Bookings Created: 5
- Cancellations: 1
- Rate Overrides: 2 (with supervisor approval)
- Guest Complaints: 1 (A/C issue - resolved)

⭐ HIGHLIGHTS:
- 100% check-in satisfaction
- VIP guest: Mr. James Wilson (Suite)
- Upsold 3 rooms from Standard to Deluxe

⚠️ ISSUES:
- Room 302 A/C repair (completed)
- Late arrival coordination (successful)

Prepared by: Sarah Johnson
Time: 23:30
```

---

## Modül 6: Problemler ve Çözümler (15 dakika)

### 6.1 Sık Karşılaşılan Durumlar

#### Durum 1: Overbooking

**Problem:** Tüm odalar dolu ama confirmed reservation var.

**Çözüm:**
```
1. Durumu manager'a escalate et
2. Guest'i bilgilendir (önce!)
3. Alternative solutions:
   - Sister hotel accommodation
   - Upgrade (next day, same hotel)
   - Full refund + compensation

4. Never: Guest'i send etmeden "we're full"
```

---

#### Durum 2: No-show

**Problem:** Guest gelmedi, booking confirmed.

**Çözüm:**
```
1. Call guest (3 attempts):
   - Immediate
   - After 2 hours
   - At 22:00

2. Check email/messages

3. If no response:
   - Mark as No-Show (after 22:00)
   - Charge no-show fee (per policy)
   - Release room for next day

4. Document everything
```

---

#### Durum 3: Guest Complaint

**Problem:** Misafir room'dan şikayet ediyor.

**Çözüm:**
```
1. Listen actively:
   "I understand, Mr. Smith. Let me help you."

2. Apologize sincerely:
   "I apologize for the inconvenience."

3. Take immediate action:
   - Engineering (technical issues)
   - Housekeeping (cleanliness)
   - Room change (if needed)

4. Follow up:
   - Call room after 30 minutes
   - "Is everything okay now?"

5. Compensation (if appropriate):
   - Complimentary breakfast
   - Room upgrade
   - Discount
   - Manager approval needed

6. Document in system:
   [Guest Profile → Add Note]
   "Jan 15 - A/C issue Room 302, resolved.
   Guest satisfied after repair."
```

**💡 Golden Rule:** Never say "No" immediately. Always offer solutions.

---

### 6.2 Sistem Hataları

#### Hata 1: Payment Failed

**Mesaj:** "Payment processing failed"

**Çözüm:**
```
1. Check card details
2. Try again
3. If fails again:
   - Ask for alternative card
   - Contact bank
   - Cash payment

4. Never keep trying same card (fraud alert!)
```

---

#### Hata 2: Room Status Not Updated

**Problem:** Housekeeping room'u clean yaptı ama sistemde dirty.

**Çözüm:**
```
1. Contact housekeeping supervisor
2. Physical verification
3. Manual update:
   [Rooms → Room 405 → Update Status → Clean]
4. Inform IT if repeated issue
```

---

## Modül 7: Best Practices (10 dakika)

### 7.1 Guest Service Excellence

**The 10-5 Rule:**
```
10 feet: Eye contact and smile 😊
5 feet: Verbal greeting "Good morning!"
```

**Phone etiquette:**
```
1. Answer within 3 rings
2. "Good morning, Front Desk. Sarah speaking.
   How may I help you?"
3. Never put guest on hold >1 minute
4. End with: "Is there anything else I can
   help you with?"
```

**Email response:**
```
- Respond within 2 hours
- Professional tone
- Clear information
- Contact details
```

---

### 7.2 Güvenlik ve Gizlilik

**Do's (Yapılması gerekenler):**
```
✅ Verify guest identity (ID check)
✅ Protect guest information (GDPR)
✅ Secure payment details
✅ Lock computer when away
✅ Report suspicious activity
```

**Don'ts (Yapılmaması gerekenler):**
```
❌ Share room numbers publicly
❌ Discuss guest details
❌ Leave credit cards visible
❌ Use same password forever
❌ Bypass security procedures
```

---

## Modül 8: Pratik Egzersizler (30 dakika)

### Egzersiz 1: Tam Check-in Süreci

**Senaryo:**
```
Guest: Ms. Emily Chen
Booking ID: BKG-TEST-001
Check-in: Today
Check-out: +3 nights
Room Type: Deluxe
Special: Honeymoon couple 💑
```

**Göreviniz:**
1. Booking'i bulun
2. Check-in yapın
3. Room assign edin (romantic room!)
4. Folio oluşturun
5. Deposit alın
6. Key card programlayın
7. Welcome speech yapın

**Süre:** 10 dakika

---

### Egzersiz 2: Problem Çözme

**Senaryo:**
```
Guest otel lobisinde:
"I booked a suite but you gave me a standard
room! This is unacceptable!"

Booking shows: Standard Room
Guest insists: Suite booked
```

**Göreviniz:**
1. Durumu analiz edin
2. Çözüm bulun
3. Guest'i memnun edin

**Süre:** 5 dakika

---

### Egzersiz 3: Multi-tasking

**Senaryo:**
```
Aynı anda:
- Guest check-in yapıyor (counter)
- Telefon çalıyor 📞
- Email geldi 📧
- Manager bir şey soruyor
```

**Göreviniz:** Öncelik sıralaması yapın ve handle edin.

**Süre:** 5 dakika

---

## 📝 Eğitim Özeti ve Sertifika

**Öğrenilen konular:**
- ✅ Sistem login ve navigasyon
- ✅ Rezervasyon oluşturma ve yönetimi
- ✅ Check-in prosedürü
- ✅ Check-out prosedürü
- ✅ Günlük operasyonlar
- ✅ Problem çözme
- ✅ Best practices

**Sertifika:**
```
╔══════════════════════════════════════════════════╗
║                                                  ║
║        RoomOps Front Desk Certification         ║
║                                                  ║
║              This certifies that                ║
║                                                  ║
║              [Employee Name]                    ║
║                                                  ║
║     has successfully completed the RoomOps      ║
║        Front Desk Training Program              ║
║                                                  ║
║              Date: January 15, 2025             ║
║              Duration: 3 hours                  ║
║                                                  ║
║         ____________________                    ║
║            Trainer Signature                    ║
║                                                  ║
╚══════════════════════════════════════════════════╝
```

---

## 📞 Destek ve Kaynaklar

**Sorularınız için:**
- IT Support: support@hotel.com (ext. 100)
- Front Office Manager: [manager@hotel.com]
- Training Materials: /docs/training/

**Online kaynaklar:**
- Video tutorials: [URL]
- FAQ: [URL]
- Quick reference guide: [Print ve masa başında tut]

---

**Eğitim tamamlandı! 🎉**

**Sonraki adımlar:**
1. ✅ Pratik yapmaya başlayın (supervisor gözetiminde)
2. ✅ İlk haftaya quick reference guide yanınızda taşıyın
3. ✅ Sorularınızı çekinmeden sorun
4. ✅ 30 gün sonra: Advanced training

**Başarılar! 🌟**

---

**Dokümantasyon güncellenme tarihi:** 15 Ocak 2025
