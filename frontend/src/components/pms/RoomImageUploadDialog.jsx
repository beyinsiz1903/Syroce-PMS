import { toast } from 'sonner';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const RoomImageUploadDialog = ({ open, onClose, selectedRoom, setSelectedRoom, onDataRefresh }) => {
  const { t } = useTranslation();

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>{t('pms.roomPhotos', 'Room Photos')} {selectedRoom ? `- ${selectedRoom.room_number}` : ''}</DialogTitle>
          <DialogDescription>
            {t('pms.roomPhotosDescription', 'Uploads to server disk in preview. For production, S3/Cloudinary is recommended.')}
          </DialogDescription>
        </DialogHeader>

        {selectedRoom ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {(selectedRoom.images || []).length === 0 ? (
                <div className="col-span-full text-sm text-gray-500">{t('pms.noPhotosYet', 'No photos uploaded yet.')}</div>
              ) : (
                (selectedRoom.images || []).map((src) => (
                  <a key={src} href={src} target="_blank" rel="noreferrer" className="block">
                    <div className="h-32 rounded-lg overflow-hidden border bg-gray-50">
                      <img src={src} alt="room" className="w-full h-full object-cover" />
                    </div>
                  </a>
                ))
              )}
            </div>

            <div className="border-t pt-4">
              <Label>{t('pms.uploadNewPhotos', 'Upload New Photo(s)')}</Label>
              <Input
                type="file"
                accept="image/*"
                multiple
                onChange={async (e) => {
                  try {
                    const files = Array.from(e.target.files || []);
                    if (files.length === 0) return;

                    const formData = new FormData();
                    files.forEach((f) => formData.append('files', f));

                    const res = await axios.post(`/pms/rooms/${selectedRoom.id}/images`, formData, {
                      headers: { 'Content-Type': 'multipart/form-data' },
                    });

                    toast.success(`${res.data.uploaded} photo(s) uploaded`);
                    await onDataRefresh();
                    setSelectedRoom(prev => prev ? ({ ...prev, images: res.data.images || prev.images }) : prev);
                  } catch (err) {
                    toast.error(err?.response?.data?.detail || 'Failed to upload photo');
                  } finally {
                    e.target.value = '';
                  }
                }}
              />
              <p className="text-[11px] text-gray-500 mt-1">JPEG/PNG/WEBP recommended. Max 10MB/file.</p>
            </div>

            <div className="flex justify-end">
              <Button variant="outline" onClick={onClose}>{t("common.close")}</Button>
            </div>
          </div>
        ) : (
          <div className="text-sm text-gray-500">{t('pms.noRoomSelected', 'No room selected.')}</div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default RoomImageUploadDialog;
