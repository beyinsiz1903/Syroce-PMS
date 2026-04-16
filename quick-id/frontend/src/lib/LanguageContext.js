import { createContext, useContext, useState, useCallback } from 'react';

const LanguageContext = createContext(null);

const translations = {
  tr: {
    // Navigation
    'nav.overview': 'Genel Bakis',
    'nav.scan': 'Tara',
    'nav.bulkScan': 'Toplu Tarama',
    'nav.guests': 'Misafirler',
    'nav.groupCheckin': 'Grup Check-in',
    'nav.rooms': 'Oda Yonetimi',
    'nav.faceMatch': 'Yuz Eslestirme',
    'nav.tcKimlik': 'TC Kimlik & Emniyet',
    'nav.monitoring': 'Monitoring',
    'nav.properties': 'Tesisler',
    'nav.kiosk': 'Kiosk & Offline',
    'nav.users': 'Kullanicilar',
    'nav.settings': 'Ayarlar & KVKK',
    'nav.kvkk': 'KVKK Uyumluluk',
    'nav.apiDocs': 'API Rehberi',
    'nav.logout': 'Cikis Yap',
    // Common
    'common.save': 'Kaydet',
    'common.cancel': 'Iptal',
    'common.delete': 'Sil',
    'common.edit': 'Duzenle',
    'common.create': 'Olustur',
    'common.refresh': 'Yenile',
    'common.search': 'Ara',
    'common.loading': 'Yukleniyor...',
    'common.noData': 'Veri bulunamadi',
    'common.confirm': 'Onayla',
    'common.back': 'Geri',
    'common.next': 'Ileri',
    'common.all': 'Tumu',
    'common.active': 'Aktif',
    'common.inactive': 'Pasif',
    'common.yes': 'Evet',
    'common.no': 'Hayir',
    'common.download': 'Indir',
    'common.downloadPdf': 'PDF Indir',
    // Login
    'login.title': 'Giris Yap',
    'login.email': 'E-posta',
    'login.password': 'Sifre',
    'login.submit': 'Giris Yap',
    'login.help': 'Giris bilgilerinizi sistem yoneticinizden alabilirsiniz.',
    'login.forgotPassword': 'Sifrenizi unuttuysaniz yoneticinize basvurun.',
    'login.locked': 'Hesap Kilitlendi',
    // Dashboard
    'dashboard.title': 'Genel Bakis',
    'dashboard.subtitle': 'Misafir giris/cikis ozeti ve son taramalar',
    'dashboard.todayCheckin': 'Bugun Check-in',
    'dashboard.todayCheckout': 'Bugun Check-out',
    'dashboard.totalGuests': 'Toplam Misafir',
    'dashboard.pendingReview': 'Inceleme Bekleyen',
    // Scan
    'scan.title': 'Kimlik Tarama',
    'scan.camera': 'Kamera',
    'scan.fileUpload': 'Dosya Yukle',
    'scan.capture': 'Yakala',
    'scan.retake': 'Yeniden Cek',
    'scan.selectFile': 'Dosya Sec',
    // Guest
    'guest.firstName': 'Ad',
    'guest.lastName': 'Soyad',
    'guest.idNumber': 'TCKN / Pasaport No',
    'guest.birthDate': 'Dogum Tarihi',
    'guest.gender': 'Cinsiyet',
    'guest.nationality': 'Uyruk',
    'guest.male': 'Erkek',
    'guest.female': 'Kadin',
    'guest.checkin': 'Check-in',
    'guest.checkout': 'Check-out',
    'guest.pending': 'Bekleyen',
    'guest.saveAsGuest': 'Misafir Olarak Kaydet',
    // Rooms
    'rooms.title': 'Oda Yonetimi',
    'rooms.available': 'Musait',
    'rooms.occupied': 'Dolu',
    'rooms.cleaning': 'Temizlik',
    'rooms.maintenance': 'Bakim',
    // Session
    'session.expiring': 'Oturum sureniz dolmak uzere',
    'session.relogin': 'Tekrar Giris Yap',
    // Theme
    'theme.light': 'Aydinlik',
    'theme.dark': 'Karanlik',
    // Email
    'email.notifications': 'E-posta Bildirimleri',
    'email.mock': 'MOCK modu (gercek e-posta gonderilmiyor)',
  },
  en: {
    // Navigation
    'nav.overview': 'Overview',
    'nav.scan': 'Scan',
    'nav.bulkScan': 'Bulk Scan',
    'nav.guests': 'Guests',
    'nav.groupCheckin': 'Group Check-in',
    'nav.rooms': 'Room Management',
    'nav.faceMatch': 'Face Match',
    'nav.tcKimlik': 'TC ID & Police',
    'nav.monitoring': 'Monitoring',
    'nav.properties': 'Properties',
    'nav.kiosk': 'Kiosk & Offline',
    'nav.users': 'Users',
    'nav.settings': 'Settings & KVKK',
    'nav.kvkk': 'KVKK Compliance',
    'nav.apiDocs': 'API Guide',
    'nav.logout': 'Sign Out',
    // Common
    'common.save': 'Save',
    'common.cancel': 'Cancel',
    'common.delete': 'Delete',
    'common.edit': 'Edit',
    'common.create': 'Create',
    'common.refresh': 'Refresh',
    'common.search': 'Search',
    'common.loading': 'Loading...',
    'common.noData': 'No data found',
    'common.confirm': 'Confirm',
    'common.back': 'Back',
    'common.next': 'Next',
    'common.all': 'All',
    'common.active': 'Active',
    'common.inactive': 'Inactive',
    'common.yes': 'Yes',
    'common.no': 'No',
    'common.download': 'Download',
    'common.downloadPdf': 'Download PDF',
    // Login
    'login.title': 'Sign In',
    'login.email': 'Email',
    'login.password': 'Password',
    'login.submit': 'Sign In',
    'login.help': 'Get your credentials from your system administrator.',
    'login.forgotPassword': 'Contact your administrator if you forgot your password.',
    'login.locked': 'Account Locked',
    // Dashboard
    'dashboard.title': 'Overview',
    'dashboard.subtitle': 'Guest check-in/out summary and recent scans',
    'dashboard.todayCheckin': 'Today Check-in',
    'dashboard.todayCheckout': 'Today Check-out',
    'dashboard.totalGuests': 'Total Guests',
    'dashboard.pendingReview': 'Pending Review',
    // Scan
    'scan.title': 'ID Scan',
    'scan.camera': 'Camera',
    'scan.fileUpload': 'File Upload',
    'scan.capture': 'Capture',
    'scan.retake': 'Retake',
    'scan.selectFile': 'Select File',
    // Guest
    'guest.firstName': 'First Name',
    'guest.lastName': 'Last Name',
    'guest.idNumber': 'ID / Passport No',
    'guest.birthDate': 'Date of Birth',
    'guest.gender': 'Gender',
    'guest.nationality': 'Nationality',
    'guest.male': 'Male',
    'guest.female': 'Female',
    'guest.checkin': 'Check-in',
    'guest.checkout': 'Check-out',
    'guest.pending': 'Pending',
    'guest.saveAsGuest': 'Save as Guest',
    // Rooms
    'rooms.title': 'Room Management',
    'rooms.available': 'Available',
    'rooms.occupied': 'Occupied',
    'rooms.cleaning': 'Cleaning',
    'rooms.maintenance': 'Maintenance',
    // Session
    'session.expiring': 'Your session is about to expire',
    'session.relogin': 'Sign In Again',
    // Theme
    'theme.light': 'Light',
    'theme.dark': 'Dark',
    // Email
    'email.notifications': 'Email Notifications',
    'email.mock': 'MOCK mode (no real emails sent)',
  },
};

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState(() => {
    try {
      return localStorage.getItem('quickid_lang') || 'tr';
    } catch { return 'tr'; }
  });

  const t = useCallback((key) => {
    return translations[lang]?.[key] || translations['tr']?.[key] || key;
  }, [lang]);

  const changeLang = useCallback((newLang) => {
    setLang(newLang);
    localStorage.setItem('quickid_lang', newLang);
  }, []);

  return (
    <LanguageContext.Provider value={{ lang, t, changeLang, availableLanguages: ['tr', 'en'] }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error('useLanguage must be used within LanguageProvider');
  return ctx;
}
