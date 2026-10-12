"""Safe, shared Meta diagnostics: never reflect provider messages or secrets."""


def meta_error_diagnostics(response, *, templates=False):
    # Never return Meta's raw body/message, headers, or exception text:
    # they can contain credentials or account information. Only accept
    # numeric diagnostic codes and map them to operator-safe guidance.
    try:
        body = response.json()
    except ValueError:
        body = None
    detail = body.get("error") if isinstance(body, dict) else None
    detail = detail if isinstance(detail, dict) else {}
    code = detail.get("code")
    subcode = detail.get("error_subcode")
    code = code if type(code) is int and 0 <= code <= 9999999 else None
    subcode = subcode if type(subcode) is int and 0 <= subcode <= 9999999 else None
    if code == 190 or response.status_code == 401:
        reason = "Erişim anahtarı geçersiz veya süresi dolmuş olabilir. Meta üzerinden anahtarı doğrulayıp yenileyin."
    elif code in (10, 200, 294) or response.status_code == 403:
        reason = "Erişim izni yetersiz. Anahtarın WhatsApp hesabına ve telefon numarasına erişimini kontrol edin."
        if templates:
            reason = "Erişim izni yetersiz. Anahtarın WABA hesabına erişimini ve whatsapp_business_management iznini kontrol edin."
    elif code == 100 or response.status_code == 404:
        reason = "Telefon numarası kimliği veya bu kaynağa erişim doğrulanamadı. Phone Number ID ve hesap yetkilerini kontrol edin."
        if templates:
            reason = "WhatsApp Business hesap kimliği veya bu kaynağa erişim doğrulanamadı. WABA ID ve hesap yetkilerini kontrol edin."
    elif code in (4, 17, 32, 613, 80007, 130429) or response.status_code == 429:
        reason = "Meta istek sınırına ulaşıldı. Bir süre sonra yeniden deneyin."
    elif response.status_code >= 500:
        reason = "Meta hizmetinde geçici hata var. Bir süre sonra yeniden deneyin."
    else:
        reason = "Meta bağlantı isteğini reddetti. Hesap yapılandırmasını ve erişim izinlerini kontrol edin."
    codes = f"HTTP {response.status_code}"
    if code is not None:
        codes += f", Meta {code}"
    if subcode is not None:
        codes += f", alt kod {subcode}"
    return {"error": f"{reason} ({codes})", "http_status": response.status_code,
            "meta_code": code, "meta_subcode": subcode}
