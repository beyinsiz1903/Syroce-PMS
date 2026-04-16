import { useState, useCallback, useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';
import CameraCapture from '../components/CameraCapture';
import ExtractionForm from '../components/ExtractionForm';
import DuplicateWarning from '../components/DuplicateWarning';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Switch } from '../components/ui/switch';
import { Label } from '../components/ui/label';
import { api } from '../lib/api';
import { Undo2, Check, Loader2, Users, Keyboard, Zap, ChevronLeft, ChevronRight } from 'lucide-react';

export default function BulkScanPage() {
  const navigate = useNavigate();
  const [allDocuments, setAllDocuments] = useState([]);
  const [currentDocIndex, setCurrentDocIndex] = useState(0);
  const [extracting, setExtracting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [scanId, setScanId] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const [scannedGuests, setScannedGuests] = useState([]);
  const [cameraKey, setCameraKey] = useState(0);
  const [autoExtract, setAutoExtract] = useState(true);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [originalExtractedList, setOriginalExtractedList] = useState([]);

  // Duplicate handling
  const [duplicateDialogOpen, setDuplicateDialogOpen] = useState(false);
  const [pendingDuplicates, setPendingDuplicates] = useState([]);

  const currentData = allDocuments[currentDocIndex] || null;

  const setCurrentData = (data) => {
    setAllDocuments(prev => {
      const updated = [...prev];
      updated[currentDocIndex] = data;
      return updated;
    });
  };

  const saveRef = useRef(null);
  saveRef.current = { allDocuments, currentDocIndex, scanId, originalExtractedList };

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        const { allDocuments: docs, currentDocIndex: idx } = saveRef.current;
        if (docs[idx] && !saving && !extracting) {
          handleSave();
        }
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
        if (document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
          e.preventDefault();
          resetForNextScan();
        }
      }
      if (e.key === 'Escape') {
        if (duplicateDialogOpen) {
          setDuplicateDialogOpen(false);
        } else {
          resetForNextScan();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [saving, extracting, duplicateDialogOpen]);

  const resetForNextScan = useCallback(() => {
    setAllDocuments([]);
    setCurrentDocIndex(0);
    setScanId(null);
    setWarnings([]);
    setOriginalExtractedList([]);
    setCameraKey(prev => prev + 1);
  }, []);

  const handleCapture = useCallback(async (imageDataUrl) => {
    if (!autoExtract) return;

    setExtracting(true);
    setAllDocuments([]);
    setCurrentDocIndex(0);
    setWarnings([]);

    try {
      const result = await api.scanId(imageDataUrl);

      if (result.success) {
        const documents = result.documents || [];
        const docCount = result.document_count || documents.length;

        if (documents.length === 0) {
          toast.error('Kimlik belgesi algılanamadı.');
          setExtracting(false);
          return;
        }

        const extractedList = documents.map(data => ({
          first_name: data.first_name || '',
          last_name: data.last_name || '',
          id_number: data.id_number || data.document_number || '',
          birth_date: data.birth_date || '',
          gender: data.gender || '',
          nationality: data.nationality || '',
          document_type: data.document_type || '',
          document_number: data.document_number || '',
          birth_place: data.birth_place || '',
          expiry_date: data.expiry_date || '',
          issue_date: data.issue_date || '',
          is_valid: data.is_valid,
          notes: '',
        }));

        setAllDocuments(extractedList);
        setOriginalExtractedList(extractedList.map(d => ({ ...d })));
        setWarnings(documents.flatMap(d => d.warnings || []));
        setScanId(result.scan?.id || null);
        setCurrentDocIndex(0);

        if (docCount > 1) {
          toast.success(`${docCount} kimlik algılandı! Sırayla kaydedin.`);
        } else if (documents[0]?.is_valid) {
          toast.success('Kimlik okundu! Ctrl+S ile kaydedin.');
        } else {
          toast.warning('Kısmi bilgi alındı, kontrol edin.');
        }
      }
    } catch (err) {
      toast.error(`Tarama hatası: ${err.message}`);
    } finally {
      setExtracting(false);
    }
  }, [autoExtract]);

  const handleSave = useCallback(async (forceCreate = false) => {
    const { allDocuments: docs, currentDocIndex: idx, scanId: sid, originalExtractedList: origList } = saveRef.current;
    const data = docs[idx];
    if (!data) return;

    setSaving(true);
    try {
      const original = origList[idx] || null;
      const payload = {
        ...data,
        scan_id: sid,
        original_extracted_data: original,
        force_create: forceCreate,
      };
      delete payload.is_valid;

      const result = await api.createGuest(payload);

      if (result.duplicate_detected && !forceCreate) {
        setPendingDuplicates(result.duplicates || []);
        setDuplicateDialogOpen(true);
        setSaving(false);
        return;
      }

      if (result.success) {
        setScannedGuests(prev => [result.guest, ...prev]);
        toast.success(`${data.first_name} ${data.last_name} kaydedildi!`);

        // If there are more documents to save, go to next
        if (idx < docs.length - 1) {
          setCurrentDocIndex(idx + 1);
          toast.info(`Sonraki kimlik (${idx + 2}/${docs.length}). Ctrl+S ile kaydedin.`);
        } else {
          // All documents saved, reset for next scan
          resetForNextScan();
        }
      }
    } catch (err) {
      toast.error(`Kaydetme hatası: ${err.message}`);
    } finally {
      setSaving(false);
    }
  }, [resetForNextScan]);

  const handleForceCreate = useCallback(async () => {
    setDuplicateDialogOpen(false);
    await handleSave(true);
  }, [handleSave]);

  const handleViewExisting = useCallback((guestId) => {
    setDuplicateDialogOpen(false);
    navigate(`/guests/${guestId}`);
  }, [navigate]);

  const undoLast = useCallback(async () => {
    if (scannedGuests.length === 0) return;
    const lastGuest = scannedGuests[0];
    try {
      await api.deleteGuest(lastGuest.id);
      setScannedGuests(prev => prev.slice(1));
      toast.info('Son misafir kaydı geri alındı.');
    } catch (err) {
      toast.error('Geri alma hatası.');
    }
  }, [scannedGuests]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-[var(--brand-ink)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            Toplu Tarama
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Ardı ardına kimlik tarayın, çoklu kimlik destekli
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="outline" className="h-9 px-4 text-base font-semibold bg-[var(--brand-sky-soft)] text-[var(--brand-sky)] border-[var(--brand-sky)]" data-testid="bulk-scan-counter">
            <Users className="w-4 h-4 mr-2" />
            {scannedGuests.length} Misafir
          </Badge>
          {scannedGuests.length > 0 && (
            <Button variant="outline" size="sm" onClick={undoLast} data-testid="bulk-scan-undo-button">
              <Undo2 className="w-4 h-4 mr-1" />
              Geri Al
            </Button>
          )}
        </div>
      </div>

      {/* Controls Bar */}
      <Card className="bg-white">
        <CardContent className="p-3">
          <div className="flex flex-wrap items-center gap-4 sm:gap-6">
            <div className="flex items-center gap-2">
              <Switch id="auto-extract" checked={autoExtract} onCheckedChange={setAutoExtract} data-testid="auto-extract-toggle" />
              <Label htmlFor="auto-extract" className="text-sm flex items-center gap-1.5 cursor-pointer">
                <Zap className="w-3.5 h-3.5 text-[var(--brand-amber)]" />
                Otomatik Çıkarım
              </Label>
            </div>
            <button
              onClick={() => setShowShortcuts(!showShortcuts)}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-[var(--brand-sky)] transition-colors"
            >
              <Keyboard className="w-3.5 h-3.5" />
              Klavye Kısayolları
            </button>
            {showShortcuts && (
              <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-[hsl(var(--secondary))] border border-[hsl(var(--border))] rounded text-[10px] font-mono">Ctrl+S</kbd>
                  Kaydet
                </span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-[hsl(var(--secondary))] border border-[hsl(var(--border))] rounded text-[10px] font-mono">Ctrl+R</kbd>
                  Sonraki Tarama
                </span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-[hsl(var(--secondary))] border border-[hsl(var(--border))] rounded text-[10px] font-mono">Esc</kbd>
                  İptal
                </span>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Main Layout */}
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(520px,1fr)_520px] gap-4">
        {/* Camera */}
        <CameraCapture key={cameraKey} onCapture={handleCapture} disabled={extracting} />

        {/* Form + Queue */}
        <div className="space-y-4">
          {extracting && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--brand-sky-soft)] text-[var(--brand-sky)] text-sm">
              <Loader2 className="w-4 h-4 animate-spin" />
              AI kimlik okuma yapılıyor...
            </div>
          )}

          {/* Multi-document navigator */}
          {allDocuments.length > 1 && (
            <Card className="bg-white">
              <CardContent className="p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Users className="w-4 h-4 text-[var(--brand-sky)]" />
                    <span className="text-sm font-medium">{allDocuments.length} kimlik algılandı</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="icon" className="h-8 w-8" disabled={currentDocIndex === 0} onClick={() => setCurrentDocIndex(i => i - 1)}>
                      <ChevronLeft className="w-4 h-4" />
                    </Button>
                    <Badge variant="outline" className="bg-[var(--brand-sky-soft)] text-[var(--brand-sky)] border-[var(--brand-sky)] px-3 font-semibold">
                      {currentDocIndex + 1} / {allDocuments.length}
                    </Badge>
                    <Button variant="outline" size="icon" className="h-8 w-8" disabled={currentDocIndex === allDocuments.length - 1} onClick={() => setCurrentDocIndex(i => i + 1)}>
                      <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
                <div className="flex gap-1.5 mt-2">
                  {allDocuments.map((doc, i) => (
                    <button
                      key={i}
                      onClick={() => setCurrentDocIndex(i)}
                      className={`flex-1 text-xs py-1.5 px-2 rounded-md transition-colors ${
                        i === currentDocIndex
                          ? 'bg-[var(--brand-sky)] text-white'
                          : 'bg-[hsl(var(--secondary))] text-muted-foreground hover:bg-[hsl(var(--border))]'
                      }`}
                    >
                      {doc.first_name || doc.last_name ? `${doc.first_name} ${doc.last_name}`.trim() : `Kimlik ${i + 1}`}
                    </button>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          <ExtractionForm
            data={currentData}
            onChange={setCurrentData}
            onSave={() => handleSave(false)}
            loading={saving}
            extracting={extracting}
            warnings={warnings}
          />

          {/* Scanned Queue */}
          {scannedGuests.length > 0 && (
            <Card className="bg-white">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Taranan Misafirler</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 max-h-64 overflow-y-auto" data-testid="bulk-scan-queue-table">
                  {scannedGuests.map((guest, i) => (
                    <div key={guest.id} className="flex items-center gap-3 p-2 rounded-lg bg-[hsl(var(--secondary))]">
                      <div className="w-7 h-7 rounded-full bg-[var(--brand-success-soft)] flex items-center justify-center">
                        <Check className="w-3.5 h-3.5 text-[var(--brand-success)]" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{guest.first_name} {guest.last_name}</p>
                        <p className="text-xs text-muted-foreground">{guest.id_number || '—'}</p>
                      </div>
                      <span className="text-xs text-muted-foreground">#{scannedGuests.length - i}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* Duplicate Warning */}
      <DuplicateWarning
        open={duplicateDialogOpen}
        onClose={() => setDuplicateDialogOpen(false)}
        duplicates={pendingDuplicates}
        onForceCreate={handleForceCreate}
        onViewExisting={handleViewExisting}
      />
    </div>
  );
}
