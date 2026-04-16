import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Skeleton } from '../components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { api } from '../lib/api';
import {
  ExternalLink,
  Copy,
  CheckCircle,
  Shield,
  Zap,
  Server,
  Lock,
  AlertTriangle,
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

export default function ApiDocsPage() {
  const [guide, setGuide] = useState(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState('');

  useEffect(() => {
    loadGuide();
  }, []);

  const loadGuide = async () => {
    try {
      const data = await api.getApiGuide();
      setGuide(data);
    } catch (err) {
      toast.error('API rehberi yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text, label) => {
    navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(''), 2000);
    toast.success('Kopyalandı');
  };

  const CodeBlock = ({ code, label }) => (
    <div className="relative group">
      <pre className="bg-[#0B1220] text-[#E2E8F0] rounded-lg p-3 text-xs overflow-x-auto font-mono leading-relaxed">
        <code>{code}</code>
      </pre>
      <button
        onClick={() => copyToClipboard(code, label)}
        className="absolute top-2 right-2 p-1.5 rounded-md bg-white/10 hover:bg-white/20 transition-colors opacity-0 group-hover:opacity-100"
      >
        {copied === label ? <CheckCircle className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5 text-white/70" />}
      </button>
    </div>
  );

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-96" />
      </div>
    );
  }

  const endpoints = guide?.endpoints || {};
  const auth = guide?.authentication || {};
  const pmsGuide = guide?.pms_integration_guide || {};
  const errorCodes = guide?.error_codes || {};

  return (
    <div className="space-y-4" data-testid="api-docs-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-[var(--brand-ink)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            API Dokümantasyonu
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Quick ID Reader API v{guide?.version} - Entegrasyon Rehberi
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => window.open(`${BACKEND_URL}/api/docs`, '_blank')}>
            <ExternalLink className="w-4 h-4 mr-1" /> Swagger UI
          </Button>
          <Button variant="outline" size="sm" onClick={() => window.open(`${BACKEND_URL}/api/redoc`, '_blank')}>
            <ExternalLink className="w-4 h-4 mr-1" /> ReDoc
          </Button>
        </div>
      </div>

      <Tabs defaultValue="quickstart" className="w-full">
        <TabsList className="grid w-full grid-cols-4 lg:w-auto lg:inline-grid">
          <TabsTrigger value="quickstart">Hızlı Başlangıç</TabsTrigger>
          <TabsTrigger value="endpoints">Endpoint'ler</TabsTrigger>
          <TabsTrigger value="pms">PMS Entegrasyon</TabsTrigger>
          <TabsTrigger value="errors">Hata Kodları</TabsTrigger>
        </TabsList>

        {/* Quick Start */}
        <TabsContent value="quickstart" className="mt-4 space-y-4">
          {/* Authentication */}
          <Card className="bg-white">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Lock className="w-4 h-4 text-[var(--brand-sky)]" />
                Kimlik Doğrulama
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Tüm korumalı endpoint'ler JWT Bearer token gerektirir. Token almak için:
              </p>
              <CodeBlock
                label="login"
                code={`POST /api/auth/login
Content-Type: application/json

{
  "email": "admin@quickid.com",
  "password": "admin123"
}

// Yanıt:
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user": { "id": "...", "email": "...", "role": "admin" }
}`}
              />
              <p className="text-sm text-muted-foreground">
                Sonraki isteklerde header'a ekleyin:
              </p>
              <CodeBlock
                label="auth-header"
                code={`Authorization: Bearer <token>`}
              />
              <div className="flex items-start gap-2 p-3 bg-[var(--brand-warning-soft)] rounded-lg">
                <AlertTriangle className="w-4 h-4 text-[var(--brand-warning)] shrink-0 mt-0.5" />
                <p className="text-xs text-[var(--brand-warning)]">
                  Token süresi {auth.token_expiry || '24 saat'}'tir. Süre dolduğunda yeniden giriş yapın.
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Quick Scan Example */}
          <Card className="bg-white">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Zap className="w-4 h-4 text-[var(--brand-sky)]" />
                Hızlı Tarama Örneği
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <CodeBlock
                label="scan-example"
                code={`POST /api/scan
Authorization: Bearer <token>
Content-Type: application/json

{
  "image_base64": "<base64_encoded_image>"
}

// Yanıt:
{
  "success": true,
  "documents": [{
    "is_valid": true,
    "document_type": "tc_kimlik",
    "first_name": "Ali",
    "last_name": "Yılmaz",
    "id_number": "12345678901",
    "birth_date": "1990-01-15",
    "gender": "M",
    "nationality": "TC"
  }],
  "confidence": {
    "overall_score": 92.5,
    "confidence_level": "high",
    "review_needed": false
  }
}`}
              />
            </CardContent>
          </Card>

          {/* Roles */}
          <Card className="bg-white">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Shield className="w-4 h-4 text-[var(--brand-sky)]" />
                Roller ve Yetkiler
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="p-3 border rounded-lg">
                  <div className="flex items-center gap-2 mb-2">
                    <Badge className="bg-[var(--brand-danger-soft)] text-[var(--brand-danger)] border border-[#FECDD3]">Admin</Badge>
                  </div>
                  <ul className="text-xs space-y-1 text-muted-foreground">
                    <li>• Tüm endpoint'lere erişim</li>
                    <li>• Kullanıcı yönetimi</li>
                    <li>• KVKK ayarları ve uyumluluk</li>
                    <li>• Veri temizliği ve anonimleştirme</li>
                    <li>• Hak talebi yönetimi</li>
                  </ul>
                </div>
                <div className="p-3 border rounded-lg">
                  <div className="flex items-center gap-2 mb-2">
                    <Badge className="bg-[var(--brand-info-soft)] text-[var(--brand-info)] border border-[#BFDBFE]">Resepsiyon</Badge>
                  </div>
                  <ul className="text-xs space-y-1 text-muted-foreground">
                    <li>• Kimlik tarama</li>
                    <li>• Misafir CRUD</li>
                    <li>• Check-in / Check-out</li>
                    <li>• Dışa aktarım</li>
                    <li>• Dashboard görüntüleme</li>
                  </ul>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Endpoints */}
        <TabsContent value="endpoints" className="mt-4 space-y-4">
          {Object.entries(endpoints).map(([category, items]) => (
            <Card key={category} className="bg-white">
              <CardHeader className="pb-2">
                <CardTitle className="text-base capitalize">
                  {category.replace(/_/g, ' ')}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {Object.entries(items).map(([name, ep]) => (
                    <div key={name} className="flex items-center gap-3 py-2 border-b last:border-0">
                      <Badge variant="outline" className={`text-[10px] font-mono shrink-0 ${
                        ep.method?.startsWith('GET') ? 'text-green-600 border-green-300' :
                        ep.method?.startsWith('POST') ? 'text-blue-600 border-blue-300' :
                        ep.method?.startsWith('PATCH') ? 'text-yellow-600 border-yellow-300' :
                        ep.method?.startsWith('DELETE') ? 'text-red-600 border-red-300' :
                        ''
                      }`}>
                        {ep.method}
                      </Badge>
                      <code className="text-xs font-mono text-[var(--brand-ink)]">{ep.path}</code>
                      {ep.description && <span className="text-xs text-muted-foreground ml-auto">{ep.description}</span>}
                      {ep.rate_limit && <Badge variant="outline" className="text-[10px]">{ep.rate_limit}</Badge>}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        {/* PMS Integration */}
        <TabsContent value="pms" className="mt-4 space-y-4">
          <Card className="bg-white">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Server className="w-4 h-4 text-[var(--brand-sky)]" />
                PMS Entegrasyon Rehberi
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {(pmsGuide.steps || []).map((step, i) => (
                  <div key={i} className="flex items-start gap-3 p-2 bg-[hsl(var(--secondary))] rounded-lg">
                    <div className="w-6 h-6 rounded-full bg-[var(--brand-sky)] flex items-center justify-center shrink-0">
                      <span className="text-xs font-bold text-white">{i + 1}</span>
                    </div>
                    <p className="text-sm">{step.replace(/^\d+\.\s*/, '')}</p>
                  </div>
                ))}
              </div>

              <div className="mt-4 p-3 bg-[var(--brand-info-soft)] rounded-lg">
                <p className="text-xs text-[var(--brand-info)]">
                  <strong>Webhook Desteği:</strong> {pmsGuide.webhook_support}
                </p>
              </div>

              <h3 className="text-sm font-semibold mt-6 mb-3">Tam Entegrasyon Akışı</h3>
              <CodeBlock
                label="pms-flow"
                code={`// 1. Token al
const login = await fetch('/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: 'admin@quickid.com', password: 'admin123' })
});
const { token } = await login.json();

// 2. Kimlik tara
const scan = await fetch('/api/scan', {
  method: 'POST',
  headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
  body: JSON.stringify({ image_base64: base64Image })
});
const { documents, confidence } = await scan.json();

// 3. Misafir oluştur
const guest = await fetch('/api/guests', {
  method: 'POST',
  headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
  body: JSON.stringify({
    ...documents[0],
    kvkk_consent: true,
    force_create: false
  })
});

// 4. Check-in
const checkin = await fetch('/api/guests/' + guestId + '/checkin', {
  method: 'POST',
  headers: { 'Authorization': 'Bearer ' + token }
});`}
              />
            </CardContent>
          </Card>
        </TabsContent>

        {/* Error Codes */}
        <TabsContent value="errors" className="mt-4">
          <Card className="bg-white">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-[var(--brand-warning)]" />
                Hata Kodları
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {Object.entries(errorCodes).map(([code, desc]) => (
                  <div key={code} className="flex items-center gap-3 py-2 border-b last:border-0">
                    <Badge variant="outline" className={`font-mono text-xs shrink-0 ${
                      code.startsWith('4') ? 'text-[var(--brand-warning)]' : 'text-[var(--brand-danger)]'
                    }`}>
                      {code}
                    </Badge>
                    <span className="text-sm">{desc}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
