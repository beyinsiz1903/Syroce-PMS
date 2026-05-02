import { useTranslation } from 'react-i18next';
import { changeLanguage as safeChangeLanguage } from '@/i18n';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { Languages } from 'lucide-react';

const languages = [
  { code: 'en', name: 'English', flag: '\ud83c\uddec\ud83c\udde7' },
  { code: 'tr', name: 'T\u00fcrk\u00e7e', flag: '\ud83c\uddf9\ud83c\uddf7' },
  { code: 'de', name: 'Deutsch', flag: '\ud83c\udde9\ud83c\uddea' },
  { code: 'fr', name: 'Fran\u00e7ais', flag: '\ud83c\uddeb\ud83c\uddf7' },
  { code: 'es', name: 'Espa\u00f1ol', flag: '\ud83c\uddea\ud83c\uddf8' },
  { code: 'it', name: 'Italiano', flag: '\ud83c\uddee\ud83c\uddf9' },
  { code: 'ru', name: '\u0420\u0443\u0441\u0441\u043a\u0438\u0439', flag: '\ud83c\uddf7\ud83c\uddfa' },
  { code: 'ar', name: '\u0627\u0644\u0639\u0631\u0628\u064a\u0629', flag: '\ud83c\uddf8\ud83c\udde6' },
  { code: 'pt', name: 'Portugu\u00eas', flag: '\ud83c\udde7\ud83c\uddf7' },
  { code: 'zh', name: '\u4e2d\u6587', flag: '\ud83c\udde8\ud83c\uddf3' }
];

const LanguageSelector = () => {
  const { i18n } = useTranslation();

  const changeLanguage = async (lng) => {
    // Paket indirilmeden önce localStorage'ı yaz (sayfa yenilenirse
    // bir sonraki mount initI18n'i doğru dille başlatır).
    localStorage.setItem('language', lng);
    await safeChangeLanguage(lng);
  };

  return (
    <div className="flex items-center gap-2">
      <Languages className="w-4 h-4 text-gray-600" />
      <Select value={i18n.language} onValueChange={changeLanguage}>
        <SelectTrigger className="w-[160px]">
          <SelectValue>
            {languages.find(l => l.code === i18n.language)?.flag}{' '}
            {languages.find(l => l.code === i18n.language)?.name}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {languages.map((lang) => (
            <SelectItem key={lang.code} value={lang.code}>
              <span className="flex items-center gap-2">
                <span>{lang.flag}</span>
                <span>{lang.name}</span>
              </span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
};

export default LanguageSelector;
