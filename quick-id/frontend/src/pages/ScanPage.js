import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import CameraCapture from '../components/CameraCapture';
import ExtractionForm from '../components/ExtractionForm';
import DuplicateWarning from '../components/DuplicateWarning';
import RoomQuickAssign from '../components/RoomQuickAssign';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Card, CardContent } from '../components/ui/card';
import { api } from '../lib/api';
import {
  Loader2, ChevronLeft, ChevronRight, Users,
  Plus, UserCheck,
} from 'lucide-react';

export default function ScanPage() {
  const navigate = useNavigate();
  const [allDocuments, setAllDocuments] = useState([]);
  const [currentDocIndex, setCurrentDocIndex] = useState(0);
  const [extracting, setExtracting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [scanId, setScanId] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const [originalExtractedList, setOriginalExtractedList] = useState([]);
  const [lastCapturedImage, setLastCapturedImage] = useState(null);

  const [duplicateDialogOpen, setDuplicateDialogOpen] = useState(false);
  const [pendingDuplicates, setPendingDuplicates] = useState([]);

  const [savedGuest, setSavedGuest] = useState(null);
  const [showRoomAssign, setShowRoomAssign] = useState(false);

  const currentData = allDocuments[currentDocIndex] || null;

  const setCurrentData = (data) => {
    setAllDocuments(prev => {
      const updated = [...prev];
      updated[currentDocIndex] = data;
      return updated;
    });
  };

  const resetForNewScan = () => {
    setAllDocuments([]);
    setCurrentDocIndex(0);
    setWarnings([]);
    setScanId(null);
    setLastCapturedImage(null);
    setSavedGuest(null);
    setShowRoomAssign(false);
    setOriginalExtractedList([]);
  };

  const handleCapture = useCallback(async (imageDataUrl) => {
    setExtracting(true);
    setAllDocuments([]);
    setCurrentDocIndex(0);
    setWarnings([]);
    setLastCapturedImage(imageDataUrl);
    setSavedGuest(null);
    setShowRoomAssign(false);

    try {
      const result = await api.scanId(imageDataUrl, null, true);

      if (result.success) {
        const documents = result.documents || [];

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
          mother_name: data.mother_name || '',
          father_name: data.father_name || '',
          is_valid: data.is_valid,
          notes: '',
        }));

        setAllDocuments(extractedList);
        setOriginalExtractedList(extractedList.map(d => ({ ...d })));
        setWarnings(documents.flatMap(d => d.warnings || []));
        setScanId(result.scan?.id || null);
        setCurrentDocIndex(0);

        if (result.fallback_used) {
          toast.warning('Offline OCR ile tarandı. Sonuçları kontrol edin.');
        } else if (documents.length > 1) {
          toast.success(`${documents.length} kimlik algılandı!`);
        } else if (documents[0]?.is_valid) {
          toast.success('Kimlik başarıyla okundu!');
        } else {
          toast.warning('Kısmi bilgi alındı, kontrol edin.');
        }
      }
    } catch (err) {
      toast.error(`Tarama hatası: ${err.message}`);
    } finally {
      setExtracting(false);
    }
  }, []);

  const handleSave = useCallback(async (forceCreate = false) => {
    if (!currentData) return;

    setSaving(true);
    try {
      const original = originalExtractedList[currentDocIndex] || null;
      const payload = {
        ...currentData,
        scan_id: scanId,
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
        toast.success(`${currentData.first_name} ${currentData.last_name} kaydedildi!`);

        if (currentDocIndex < allDocuments.length - 1) {
          setCurrentDocIndex(prev => prev + 1);
          toast.info('Sonraki kimlik bilgilerini kontrol edin.');
        } else {
          setSavedGuest({
            id: result.guest.id,
            name: `${currentData.first_name} ${currentData.last_name}`.trim(),
          });
          setShowRoomAssign(true);
        }
      }
    } catch (err) {
      toast.error(`Kaydetme hatası: ${err.message}`);
    } finally {
      setSaving(false);
    }
  }, [currentData, currentDocIndex, allDocuments, scanId, originalExtractedList]);

  const handleForceCreate = useCallback(async () => {
    setDuplicateDialogOpen(false);
    await handleSave(true);
  }, [handleSave]);

  const handleViewExisting = useCallback((guestId) => {
    setDuplicateDialogOpen(false);
    navigate(`/guests/${guestId}`);
  }, [navigate]);

  const handleRoomAssigned = (roomNumber) => {
    toast.success(`Oda ${roomNumber} atandı!`);
  };

  const handleSkipRoom = () => {
    navigate(`/guests/${savedGuest.id}`);
  };

  if (showRoomAssign && savedGuest) {
    return (
      <div className="space-y-4 max-w-lg mx-auto">
        <div className="text-center">
          <div className="w-14 h-14 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-3">
            <UserCheck className="w-7 h-7 text-green-600" />
          </div>
          <h2 className="text-xl font-semibold text-[var(--brand-ink)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            {savedGuest.name}
          </h2>
          <p className="text-sm text-muted-foreground mt-1">Misafir kaydedildi. Şimdi oda atayabilirsiniz.</p>
        </div>

        <RoomQuickAssign
          guestId={savedGuest.id}
          guestName={savedGuest.name}
          onComplete={handleRoomAssigned}
          onSkip={handleSkipRoom}
        />

        <div className="flex justify-center gap-3 pt-2">
          <Button variant="outline" size="sm" onClick={resetForNewScan}>
            <Plus className="w-4 h-4 mr-1" />
            Yeni Tarama
          </Button>
          <Button variant="outline" size="sm" onClick={() => navigate(`/guests/${savedGuest.id}`)}>
            <UserCheck className="w-4 h-4 mr-1" />
            Misafir Detayı
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--brand-ink)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
          Kimlik Tarama
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Kimlik kartını kameraya gösterin, bilgiler otomatik okunacak
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(520px,1fr)_520px] gap-4">
        <CameraCapture onCapture={handleCapture} disabled={extracting} />

        <div>
          {extracting && (
            <div className="mb-3 flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--brand-sky-soft)] text-[var(--brand-sky)] text-sm">
              <Loader2 className="w-4 h-4 animate-spin" />
              Kimlik okunuyor...
            </div>
          )}

          {allDocuments.length > 1 && (
            <Card className="bg-white mb-3">
              <CardContent className="p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Users className="w-4 h-4 text-[var(--brand-sky)]" />
                    <span className="text-sm font-medium">
                      {allDocuments.length} kimlik algılandı
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-8 w-8"
                      disabled={currentDocIndex === 0}
                      onClick={() => setCurrentDocIndex(i => i - 1)}
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </Button>
                    <Badge variant="outline" className="bg-[var(--brand-sky-soft)] text-[var(--brand-sky)] border-[var(--brand-sky)] px-3 font-semibold">
                      {currentDocIndex + 1} / {allDocuments.length}
                    </Badge>
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-8 w-8"
                      disabled={currentDocIndex === allDocuments.length - 1}
                      onClick={() => setCurrentDocIndex(i => i + 1)}
                    >
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
                      {doc.first_name || doc.last_name
                        ? `${doc.first_name} ${doc.last_name}`.trim()
                        : `Kimlik ${i + 1}`}
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
            warnings={currentData ? (allDocuments[currentDocIndex]?.warnings || warnings) : warnings}
          />
        </div>
      </div>

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
