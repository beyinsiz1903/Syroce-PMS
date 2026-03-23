import { useState, useCallback } from 'react';
import axios from 'axios';
import { enqueueMediaUpload } from '@/utils/offlineQueueDB';

const MEDIA_SYNC_TAG = 'sync-media-uploads';

const registerBackgroundSync = async (tag = MEDIA_SYNC_TAG) => {
  if (
    typeof window === 'undefined' ||
    !('serviceWorker' in navigator) ||
    !('SyncManager' in window)
  ) {
    return;
  }

  const registration = await navigator.serviceWorker.ready;
  try {
    await registration.sync.register(tag);
  } catch (error) {
    console.warn('[MediaCapture] Sync registration failed', error);
  }
};

const uploadToStorage = async (uploadUrl, headers, file) => {
  const normalizedHeaders = new Headers(headers || {});
  if (file?.type && !normalizedHeaders.has('Content-Type')) {
    normalizedHeaders.set('Content-Type', file.type);
  }

  const response = await fetch(uploadUrl, {
    method: 'PUT',
    headers: normalizedHeaders,
    body: file
  });

  if (!response.ok) {
    throw new Error(`Storage upload failed with status ${response.status}`);
  }
};

const buildFileName = (file) => {
  if (file?.name) return file.name;
  const extension = file?.type?.split('/')[1] || 'jpg';
  return `capture-${Date.now()}.${extension}`;
};

export default function useMediaCapture() {
  const [uploading, setUploading] = useState(false);

  const uploadMedia = useCallback(
    async ({
      file,
      module,
      entityId,
      mediaType = 'photo',
      qaRequired = false,
      metadata = {}
    }) => {
      if (!file) {
        throw new Error('File is required');
      }
      if (!module || !entityId) {
        throw new Error('module and entityId are required');
      }

      setUploading(true);
      const authToken = localStorage.getItem('token')?.replace('Bearer ', '') || null;
      const requestPayload = {
        module,
        entity_id: entityId,
        filename: buildFileName(file),
        content_type: file.type || 'image/jpeg',
        size_bytes: file.size,
        media_type: mediaType,
        qa_required: qaRequired,
        metadata
      };

      let responseData = null;

      try {
        const { data } = await axios.post('/media/request-upload', requestPayload);
        responseData = data;

        await uploadToStorage(data.upload_url, data.headers, file);

        await axios.post('/media/confirm', {
          media_id: data.media_id,
          storage_url: data.upload_url,
          size_bytes: file.size,
          content_type: file.type,
          metadata
        });

        return { success: true, offlineQueued: false, mediaId: data.media_id };
      } catch (error) {
        console.warn('[MediaCapture] Upload failed, queueing for sync', error);

        const queuedId = crypto.randomUUID();
        await enqueueMediaUpload({
          id: queuedId,
          module,
          entityId,
          file,
          contentType: file.type || 'image/jpeg',
          uploadUrl: responseData?.upload_url || null,
          headers: responseData?.headers || null,
          mediaId: responseData?.media_id || null,
          metadata,
          qaRequired,
          requestPayload,
          confirmPayload: {
            media_id: responseData?.media_id || null,
            storage_url: responseData?.upload_url || null,
            size_bytes: file.size,
            content_type: file.type,
            metadata
          },
          authToken
        });

        await registerBackgroundSync(MEDIA_SYNC_TAG);

        return { success: true, offlineQueued: true, mediaId: responseData?.media_id || queuedId };
      } finally {
        setUploading(false);
      }
    },
    []
  );

  return { uploadMedia, uploading };
}
