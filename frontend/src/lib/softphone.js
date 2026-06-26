/**
 * Softphone tek-tıkla arama yardımcıları.
 *
 * Misafir/rezervasyon/folyo ekranlarındaki "Ara" düğmeleri ile global Softphone
 * bileşenini gevşek bağlı (loosely-coupled) bir CustomEvent üzerinden bağlar:
 * buton ``syroce:softphone-dial`` yayar, Softphone dinler ve numarayı doldurup
 * (mümkünse) çağrıyı başlatır. Bu sayede arayan ekranların Softphone'a doğrudan
 * referansı / prop-drilling olmaz.
 */

export const SOFTPHONE_DIAL_EVENT = "syroce:softphone-dial";

/**
 * Ham telefon numarasını çevrilebilir biçime indirger: yalnız rakamlar ve (varsa)
 * baştaki ``+`` korunur. Sunucu tarafı (sanitize_dial_number) ayrıca doğrular;
 * burada yalnız görsel/biçim gürültüsünü (boşluk, tire, parantez) temizleriz.
 */
export function normalizeDialNumber(raw) {
  if (!raw) return "";
  const s = String(raw).trim();
  const hasPlus = s.startsWith("+");
  const digits = s.replace(/\D/g, "");
  if (!digits) return "";
  return (hasPlus ? "+" : "") + digits;
}

/**
 * Verilen numarayla Softphone'u tetikler. Numara geçersizse hiçbir şey yapmaz.
 */
export function dialViaSoftphone(number) {
  const normalized = normalizeDialNumber(number);
  if (!normalized) return;
  window.dispatchEvent(
    new CustomEvent(SOFTPHONE_DIAL_EVENT, { detail: { number: normalized } }),
  );
}
