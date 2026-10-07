type QuickIdErrorLike = {
  status?: number;
  message?: string;
  data?: unknown;
};

const QUALITY_GUIDANCE =
  'Kimlik bilgileri okunamadı. Belgeyi düz zemine koyun; dört köşe görünsün, ışık yansıması ve bulanıklık olmasın, ardından yeniden çekin.';

function errorParts(error: unknown): { status: number | null; text: string } {
  if (!error || typeof error !== 'object') {
    return { status: null, text: typeof error === 'string' ? error : '' };
  }
  const value = error as QuickIdErrorLike;
  let dataText = '';
  try {
    dataText = value.data == null ? '' : JSON.stringify(value.data);
  } catch {
    dataText = '';
  }
  return {
    status: typeof value.status === 'number' ? value.status : null,
    text: `${value.message || ''} ${dataText}`.trim(),
  };
}

/** Convert camera/OCR transport failures into safe, actionable operator copy. */
export function quickIdErrorMessage(error: unknown): string {
  const { status, text } = errorParts(error);
  const normalized = text.toLocaleLowerCase('tr-TR');

  if (status === 0 || /network|bağlantı|ulaşılamıyor|internet|request_timeout/.test(normalized)) {
    return 'Kimlik tarama servisine bağlanılamadı. İnternet bağlantısını kontrol edip yeniden deneyin.';
  }
  if (status === 401) return 'Oturumunuz sona erdi. Yeniden giriş yapıp kimliği tekrar okutun.';
  if (status === 403) return 'Bu işlem için Quick‑ID yetkiniz bulunmuyor. Yöneticinizden erişim isteyin.';
  if (status === 413 || /çok büyük|too large/.test(normalized)) {
    return 'Fotoğraf boyutu çok büyük. Kamerayı yeniden açıp kimliği ekrana daha yakın çekin.';
  }
  if (status === 504 || /zaman aşım|timeout/.test(normalized)) {
    return 'Kimlik okuma zaman aşımına uğradı. Birkaç saniye sonra yeniden deneyin.';
  }
  if (status === 503 || /sağlayıcı|api anahtarı|kullanılamıyor|devre dışı/.test(normalized)) {
    return 'Kimlik okuma servisi şu anda hazır değil. Daha sonra yeniden deneyin veya bilgileri elle girin.';
  }
  if (
    status === 422 ||
    /okunabilir|okunamadı|güvenilir|bulanık|net fotoğraf|kimlik alanları|görüntü/.test(normalized)
  ) {
    return QUALITY_GUIDANCE;
  }
  if (/permission|izin|camera|kamera/.test(normalized)) {
    return 'Kamera açılamadı. Cihaz ayarlarından Syroce PMS için kamera iznini etkinleştirin.';
  }
  return 'Kimlik okunamadı. Fotoğrafı yeniden çekin veya bilgileri elle girin.';
}

export { QUALITY_GUIDANCE };
