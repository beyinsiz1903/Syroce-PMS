import { File } from 'expo-file-system';

import { apiRequest } from './client';
import { normalizeQuickIdResponse, type QuickIdApiResponse } from '../utils/quickidResponse';

export { normalizeQuickIdResponse } from '../utils/quickidResponse';

export type QuickIdResult = {
  first_name?: string;
  last_name?: string;
  full_name?: string;
  id_number?: string;
  passport_number?: string;
  nationality?: string;
  birth_date?: string;
  document_type?: string;
};

export async function scanIdPhoto(uri: string): Promise<QuickIdResult> {
  // The authenticated PMS proxy accepts JSON/base64, not multipart. Reading
  // the picker file through Expo's native File API also works for iOS ph/file
  // URIs without leaking the image to a public Quick-ID service.
  const imageBase64 = await new File(uri).base64();
  if (!imageBase64) throw new Error('Kimlik fotoğrafı okunamadı. Lütfen yeniden çekin.');

  const data = await apiRequest<QuickIdApiResponse>('/api/quick-id/scan', {
    method: 'POST',
    body: { image_base64: imageBase64, smart_mode: true },
    // Hosted vision providers and fallback OCR can legitimately exceed the
    // normal 15-second API budget. Backend scan timeout is 60 seconds.
    timeoutMs: 70_000,
  });
  return normalizeQuickIdResponse(data);
}
