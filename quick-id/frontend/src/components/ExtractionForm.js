import { useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Button } from './ui/button';
import { Textarea } from './ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Badge } from './ui/badge';
import { Skeleton } from './ui/skeleton';
import { Save, Loader2, AlertCircle, CheckCircle2, ChevronDown, ChevronUp } from 'lucide-react';

const DOC_TYPES = [
  { value: 'tc_kimlik', label: 'TC Kimlik' },
  { value: 'passport', label: 'Pasaport' },
  { value: 'drivers_license', label: 'Ehliyet' },
  { value: 'old_nufus_cuzdani', label: 'Eski Nüfus Cüzdanı' },
  { value: 'other', label: 'Diğer' },
];

const GENDER_OPTIONS = [
  { value: 'M', label: 'Erkek' },
  { value: 'F', label: 'Kadın' },
];

export default function ExtractionForm({ data, onChange, onSave, loading, extracting, warnings }) {
  const [showDetails, setShowDetails] = useState(false);

  const validation = useMemo(() => {
    if (!data) return { valid: false, errors: [], filledCount: 0, totalRequired: 3 };
    const errors = [];
    
    if (!data.first_name?.trim()) errors.push('Ad gerekli');
    if (!data.last_name?.trim()) errors.push('Soyad gerekli');
    if (!data.id_number?.trim()) errors.push('Kimlik numarası gerekli');
    
    if (data.birth_date && !/^\d{4}-\d{2}-\d{2}$/.test(data.birth_date)) {
      errors.push('Doğum tarihi formatı geçersiz (YYYY-MM-DD)');
    }
    if (data.expiry_date && !/^\d{4}-\d{2}-\d{2}$/.test(data.expiry_date)) {
      errors.push('Geçerlilik tarihi formatı geçersiz');
    }
    if (data.id_number?.trim() && data.document_type === 'tc_kimlik' && data.id_number.trim().length !== 11) {
      errors.push('TC Kimlik No 11 haneli olmalı');
    }

    const filledFields = [data.first_name, data.last_name, data.id_number].filter(v => v?.trim()).length;

    return {
      valid: errors.length === 0 && filledFields >= 3,
      errors,
      filledCount: filledFields,
      totalRequired: 3,
    };
  }, [data]);

  if (extracting) {
    return (
      <Card className="bg-white">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin text-[var(--brand-sky)]" />
            Kimlik okunuyor...
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="space-y-1.5">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-9 w-full" />
            </div>
          ))}
        </CardContent>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card className="bg-white">
        <CardContent className="flex flex-col items-center justify-center py-16">
          <div className="w-16 h-16 rounded-full bg-[hsl(var(--secondary))] flex items-center justify-center mb-4">
            <AlertCircle className="w-8 h-8 text-muted-foreground" />
          </div>
          <p className="text-sm text-muted-foreground text-center">
            Kimlik kartını kameraya gösterin,<br />bilgiler otomatik okunacak.
          </p>
        </CardContent>
      </Card>
    );
  }

  const handleChange = (field, value) => {
    if (onChange) {
      onChange({ ...data, [field]: value });
    }
  };

  const showFieldError = (field) => {
    if (!data) return false;
    return data[field] !== undefined && data[field] !== null && !data[field]?.toString().trim();
  };

  const hasDetailData = data.birth_place || data.issue_date || data.expiry_date || data.mother_name || data.father_name || data.notes || data.document_number;

  return (
    <Card className="bg-white">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Kimlik Bilgileri</CardTitle>
          {data.is_valid === false && (
            <Badge variant="outline" className="bg-[var(--brand-warning-soft)] text-[var(--brand-warning)] border-[#FED7AA]">
              Kontrol Edin
            </Badge>
          )}
        </div>
        {warnings && warnings.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1">
            {warnings.map((w, i) => (
              <span key={i} className="text-xs text-[var(--brand-warning)] bg-[var(--brand-warning-soft)] px-2 py-0.5 rounded-full">
                {w}
              </span>
            ))}
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Belge Türü</Label>
          <Select
            value={data.document_type || ''}
            onValueChange={(v) => handleChange('document_type', v)}
          >
            <SelectTrigger data-testid="guest-document-type-select">
              <SelectValue placeholder="Belge türü seçin" />
            </SelectTrigger>
            <SelectContent>
              {DOC_TYPES.map((t) => (
                <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Ad <span className="text-red-400">*</span></Label>
            <Input
              value={data.first_name || ''}
              onChange={(e) => handleChange('first_name', e.target.value)}
              placeholder="Ad"
              data-testid="guest-first-name-input"
              className={showFieldError('first_name') ? 'border-red-300 focus:ring-red-200' : ''}
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Soyad <span className="text-red-400">*</span></Label>
            <Input
              value={data.last_name || ''}
              onChange={(e) => handleChange('last_name', e.target.value)}
              placeholder="Soyad"
              data-testid="guest-last-name-input"
              className={showFieldError('last_name') ? 'border-red-300 focus:ring-red-200' : ''}
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">TCKN / Pasaport No <span className="text-red-400">*</span></Label>
          <Input
            value={data.id_number || ''}
            onChange={(e) => handleChange('id_number', e.target.value)}
            placeholder="Kimlik numarası"
            data-testid="guest-document-number-input"
            className={showFieldError('id_number') ? 'border-red-300 focus:ring-red-200' : ''}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Doğum Tarihi</Label>
            <Input
              type="date"
              value={data.birth_date || ''}
              onChange={(e) => handleChange('birth_date', e.target.value)}
              data-testid="guest-birthdate-input"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Cinsiyet</Label>
            <Select
              value={data.gender || ''}
              onValueChange={(v) => handleChange('gender', v)}
            >
              <SelectTrigger data-testid="guest-gender-select">
                <SelectValue placeholder="Seçin" />
              </SelectTrigger>
              <SelectContent>
                {GENDER_OPTIONS.map((g) => (
                  <SelectItem key={g.value} value={g.value}>{g.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Uyruk</Label>
          <Input
            value={data.nationality || ''}
            onChange={(e) => handleChange('nationality', e.target.value)}
            placeholder="Uyruk"
            data-testid="guest-nationality-input"
          />
        </div>

        <button
          type="button"
          onClick={() => setShowDetails(!showDetails)}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-[var(--brand-ink)] transition-colors w-full py-1"
        >
          {showDetails ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          {showDetails ? 'Detayları gizle' : 'Diğer bilgiler'}
          {hasDetailData && !showDetails && (
            <Badge variant="outline" className="text-[10px] ml-1 px-1.5 py-0 text-muted-foreground">dolu</Badge>
          )}
        </button>

        {showDetails && (
          <div className="space-y-3 pt-1 border-t border-dashed">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Belge No</Label>
              <Input
                value={data.document_number || ''}
                onChange={(e) => handleChange('document_number', e.target.value)}
                placeholder="Belge numarası"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Doğum Yeri</Label>
              <Input
                value={data.birth_place || ''}
                onChange={(e) => handleChange('birth_place', e.target.value)}
                placeholder="Doğum yeri"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Anne Adı</Label>
                <Input
                  value={data.mother_name || ''}
                  onChange={(e) => handleChange('mother_name', e.target.value)}
                  placeholder="Anne adı"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Baba Adı</Label>
                <Input
                  value={data.father_name || ''}
                  onChange={(e) => handleChange('father_name', e.target.value)}
                  placeholder="Baba adı"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Veriliş Tarihi</Label>
                <Input
                  type="date"
                  value={data.issue_date || ''}
                  onChange={(e) => handleChange('issue_date', e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Geçerlilik Tarihi</Label>
                <Input
                  type="date"
                  value={data.expiry_date || ''}
                  onChange={(e) => handleChange('expiry_date', e.target.value)}
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Not</Label>
              <Textarea
                value={data.notes || ''}
                onChange={(e) => handleChange('notes', e.target.value)}
                placeholder="Ek notlar..."
                rows={2}
              />
            </div>
          </div>
        )}

        {!validation.valid && data.first_name !== undefined && (
          <div className="flex items-start gap-2 p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-700 text-xs">
            <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            <div>
              <p className="font-medium">Eksik alanlar ({validation.filledCount}/{validation.totalRequired})</p>
              {validation.errors.slice(0, 3).map((err, i) => (
                <p key={i} className="mt-0.5">{err}</p>
              ))}
            </div>
          </div>
        )}

        <Button
          onClick={onSave}
          disabled={loading || !validation.valid}
          className="w-full bg-[var(--brand-sky)] hover:bg-[#094C6E] text-white mt-2"
          data-testid="scan-save-button"
        >
          {loading ? (
            <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Kaydediliyor...</>
          ) : validation.valid ? (
            <><CheckCircle2 className="w-4 h-4 mr-2" /> Kaydet ve Oda Ata</>
          ) : (
            <><Save className="w-4 h-4 mr-2" /> Kaydet ve Oda Ata</>
          )}
        </Button>
      </CardContent>
    </Card>
  );
}
