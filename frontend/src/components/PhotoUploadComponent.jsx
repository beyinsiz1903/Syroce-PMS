import React, { useState } from 'react';
import { Camera, Upload, X, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import useMediaCapture from '@/hooks/useMediaCapture';

const PhotoUploadComponent = ({
  roomId,
  roomNumber,
  photoType = 'before',
  onUploadComplete,
  showNotes = true
}) => {
  const [photo, setPhoto] = useState(null);
  const [preview, setPreview] = useState(null);
  const [qualityScore, setQualityScore] = useState(photoType === 'after' ? 9 : 0);
  const [notes, setNotes] = useState('');
  const { uploadMedia, uploading } = useMediaCapture();

  const handleCapture = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setPreview(reader.result);
        setPhoto(file);
      };
      reader.readAsDataURL(file);
    }
  };

  const uploadPhoto = async () => {
    if (!photo || !roomId) {
      toast.error('Fotoğraf veya oda seçimi eksik');
      return;
    }

    try {
      const metadata = {
        room_id: roomId,
        room_number: roomNumber,
        photo_type: photoType,
        notes: showNotes ? notes.trim() : undefined,
        quality_score: photoType === 'after' ? qualityScore : undefined,
        captured_at: new Date().toISOString()
      };

      const result = await uploadMedia({
        file: photo,
        module: 'housekeeping',
        entityId: roomId,
        mediaType: 'photo',
        qaRequired: photoType !== 'before',
        metadata
      });

      if (result.offlineQueued) {
        toast.message('📶 Fotoğraf sıraya alındı', {
          description: 'Bağlantı geldiğinde otomatik yükleme yapılacak.'
        });
      } else {
        toast.success(`✓ ${photoType === 'before' ? 'Önce' : 'Sonra'} fotoğrafı yüklendi!`);
      }

      setPhoto(null);
      setPreview(null);
      setNotes('');
      if (onUploadComplete) onUploadComplete(result);
    } catch (error) {
      console.error('Media upload failed', error);
      toast.error('Fotoğraf yüklenemedi');
    }
  };

  const getTitle = () => {
    if (photoType === 'before') return '📷 Önce Fotoğrafı';
    if (photoType === 'after') return '✅ Sonra Fotoğrafı';
    if (photoType === 'issue') return '⚠️ Hasar Kaydı';
    return '📸 Fotoğraf';
  };

  return (
    <Card className="border-2 border-dashed border-gray-300">
      <CardContent className="p-4">
        <div className="text-center">
          <p className="font-semibold mb-2">{getTitle()}</p>
          <p className="text-xs text-gray-600 mb-3">Oda {roomNumber}</p>

          {!preview ? (
            <label className="cursor-pointer">
              <div className="flex flex-col items-center justify-center h-40 bg-gray-50 rounded-lg hover:bg-gray-100 transition">
                <Camera className="w-12 h-12 text-gray-400 mb-2" />
                <p className="text-sm text-gray-600">Fotoğraf Çek</p>
              </div>
              <input
                type="file"
                accept="image/*"
                capture="environment"
                onChange={handleCapture}
                className="hidden"
              />
            </label>
          ) : (
            <div className="space-y-3">
              <div className="relative">
                <img 
                  src={preview} 
                  alt="Preview" 
                  className="w-full h-48 object-cover rounded-lg"
                />
                <Button
                  size="icon"
                  variant="destructive"
                  className="absolute top-2 right-2"
                  onClick={() => {
                    setPhoto(null);
                    setPreview(null);
                  }}
                >
                  <X className="w-4 h-4" />
                </Button>
              </div>
              <Button 
                className="w-full bg-green-600 hover:bg-green-700"
                onClick={uploadPhoto}
                disabled={uploading}
              >
                {uploading ? (
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Upload className="w-4 h-4 mr-2" />
                )}
                Yükle
              </Button>
              {photoType === 'after' && (
                <div className="text-left space-y-2">
                  <Label className="text-xs text-gray-600">Kalite Skoru: {qualityScore}/10</Label>
                  <input
                    type="range"
                    min="1"
                    max="10"
                    value={qualityScore}
                    onChange={(e) => setQualityScore(Number(e.target.value))}
                    className="w-full"
                  />
                </div>
              )}
              {showNotes && (
                <div className="text-left space-y-2">
                  <Label className="text-xs text-gray-600">Notlar</Label>
                  <Textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    rows={2}
                    placeholder="Lekeler, bakım notları..."
                  />
                </div>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default PhotoUploadComponent;