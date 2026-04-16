"""
Geliştirilmiş Görüntü Kalite Kontrolü Modülü
- Bulanıklık tespiti (Laplacian variance)
- Karanlık/aşırı parlak görüntü tespiti
- Çözünürlük kontrolü
- Kontrast kontrolü
- Parlama/yansıma (glare) tespiti
- Belge kenar tespiti
- Eğiklik/rotasyon tespiti
- Otomatik iyileştirme önerileri
- Ağırlıklı puanlama
"""
import base64
import io
import math
from typing import Optional

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    np = None

try:
    from PIL import Image, ImageEnhance, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def decode_base64_image(image_base64: str) -> Optional[object]:
    """Base64 görüntüyü numpy array'e çevir"""
    if not CV2_AVAILABLE:
        return None
    try:
        if "," in image_base64:
            image_base64 = image_base64.split(",")[1]
        img_bytes = base64.b64decode(image_base64)
        img_array = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None


def check_blur(img: object, threshold: float = 100.0) -> dict:
    """Bulanıklık kontrolü - Laplacian variance yöntemi"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    is_blurry = laplacian_var < threshold

    if laplacian_var < 50:
        level = "very_blurry"
        message = "Görüntü çok bulanık. Lütfen kamerayı sabit tutun ve odaklanmasını bekleyin."
        score_penalty = 35
    elif laplacian_var < 100:
        level = "blurry"
        message = "Görüntü bulanık. Daha net bir fotoğraf çekmeyi deneyin."
        score_penalty = 20
    elif laplacian_var < 200:
        level = "acceptable"
        message = "Görüntü netliği kabul edilebilir."
        score_penalty = 5
    else:
        level = "sharp"
        message = "Görüntü netliği iyi."
        score_penalty = 0

    return {
        "is_blurry": is_blurry,
        "blur_score": round(laplacian_var, 2),
        "blur_level": level,
        "message": message,
        "score_penalty": score_penalty,
    }


def check_brightness(img: object) -> dict:
    """Aydınlatma kontrolü"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mean_brightness = np.mean(gray)

    if mean_brightness < 50:
        level = "very_dark"
        message = "Görüntü çok karanlık. Lütfen daha aydınlık bir ortamda çekin veya flaş kullanın."
        is_ok = False
        score_penalty = 30
    elif mean_brightness < 80:
        level = "dark"
        message = "Görüntü karanlık. Aydınlatmayı artırmayı deneyin."
        is_ok = False
        score_penalty = 15
    elif mean_brightness > 220:
        level = "overexposed"
        message = "Görüntü aşırı parlak. Flaşı kapatın veya ışık kaynağından uzaklaşın."
        is_ok = False
        score_penalty = 25
    elif mean_brightness > 200:
        level = "bright"
        message = "Görüntü biraz parlak ama kabul edilebilir."
        is_ok = True
        score_penalty = 5
    else:
        level = "good"
        message = "Aydınlatma uygun."
        is_ok = True
        score_penalty = 0

    return {
        "brightness_ok": is_ok,
        "brightness_score": round(float(mean_brightness), 2),
        "brightness_level": level,
        "message": message,
        "score_penalty": score_penalty,
    }


def check_resolution(img: object, min_width: int = 640, min_height: int = 480) -> dict:
    """Çözünürlük kontrolü"""
    height, width = img.shape[:2]
    is_ok = width >= min_width and height >= min_height

    if not is_ok:
        message = f"Görüntü çözünürlüğü düşük ({width}x{height}). En az {min_width}x{min_height} olmalı."
        score_penalty = 20
    elif width < 1280 or height < 960:
        message = f"Çözünürlük kabul edilebilir ({width}x{height}). Daha iyi sonuç için daha yüksek çözünürlük önerilir."
        score_penalty = 5
    else:
        message = f"Çözünürlük yeterli ({width}x{height})."
        score_penalty = 0

    return {
        "resolution_ok": is_ok,
        "width": width,
        "height": height,
        "message": message,
        "score_penalty": score_penalty,
    }


def check_contrast(img: object) -> dict:
    """Kontrast kontrolü"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    contrast = float(np.std(gray))

    if contrast < 30:
        level = "low"
        message = "Görüntü kontrastı düşük. Belge ve arka plan arasında yeterli kontrast yok."
        is_ok = False
        score_penalty = 20
    elif contrast < 50:
        level = "acceptable"
        message = "Kontrast kabul edilebilir."
        is_ok = True
        score_penalty = 5
    else:
        level = "good"
        message = "Kontrast iyi."
        is_ok = True
        score_penalty = 0

    return {
        "contrast_ok": is_ok,
        "contrast_score": round(contrast, 2),
        "contrast_level": level,
        "message": message,
        "score_penalty": score_penalty,
    }


def check_glare(img: object) -> dict:
    """Parlama/yansıma (glare) tespiti"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Çok parlak bölgeleri tespit et (threshold > 240)
    _, bright_mask = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
    bright_pixels = np.count_nonzero(bright_mask)
    total_pixels = gray.shape[0] * gray.shape[1]
    bright_ratio = bright_pixels / total_pixels

    # Parlak bölgelerin yoğunluğunu kontrol et (kümelenmiş parlama)
    has_glare = False
    glare_regions = 0

    if bright_ratio > 0.01:  # En az %1 parlak piksel varsa kontür ara
        contours, _ = cv2.findContours(bright_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        # Büyük parlak bölgeler
        large_bright_areas = [c for c in contours if cv2.contourArea(c) > total_pixels * 0.005]
        glare_regions = len(large_bright_areas)
        has_glare = glare_regions > 0

    if has_glare and bright_ratio > 0.05:
        level = "severe"
        message = f"Ciddi parlama tespit edildi ({glare_regions} bölge). Flaşı kapatın veya açıyı değiştirin."
        score_penalty = 25
    elif has_glare:
        level = "moderate"
        message = f"Hafif parlama tespit edildi ({glare_regions} bölge). Sonuçları etkileyebilir."
        score_penalty = 10
    elif bright_ratio > 0.02:
        level = "minor"
        message = "Çok az parlama var, sonuçları etkilemez."
        score_penalty = 3
    else:
        level = "none"
        message = "Parlama tespit edilmedi."
        score_penalty = 0

    return {
        "has_glare": has_glare,
        "glare_level": level,
        "bright_ratio": round(bright_ratio * 100, 2),
        "glare_regions": glare_regions,
        "message": message,
        "score_penalty": score_penalty,
    }


def check_document_edges(img: object) -> dict:
    """Belge kenar tespiti - belgenin tam görünüp görünmediğini kontrol et"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape

    # Kenar tespiti
    edges = cv2.Canny(gray, 50, 150)

    # Dilation ile kenarları birleştir
    kernel = np.ones((5, 5), np.uint8)
    dilated = cv2.dilate(edges, kernel, iterations=2)

    # Kontürleri bul
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return {
            "edges_detected": False,
            "document_visible": False,
            "coverage_percent": 0,
            "message": "Belge kenarları tespit edilemedi. Belgenin tamamını çerçeveye alın.",
            "score_penalty": 15,
        }

    # En büyük kontürü bul
    largest_contour = max(contours, key=cv2.contourArea)
    contour_area = cv2.contourArea(largest_contour)
    image_area = width * height
    coverage = contour_area / image_area * 100

    # 4 köşeli şekil algılama (belge dörtgen olmalı)
    epsilon = 0.02 * cv2.arcLength(largest_contour, True)
    approx = cv2.approxPolyDP(largest_contour, epsilon, True)
    is_rectangular = len(approx) == 4

    if coverage < 15:
        message = "Belge çok küçük görünüyor. Belgeye yaklaşın."
        score_penalty = 15
        document_visible = False
    elif coverage > 90:
        message = "Belge çerçevenin neredeyse tamamını kaplıyor. Biraz uzaklaşın."
        score_penalty = 5
        document_visible = True
    elif coverage >= 30:
        if is_rectangular:
            message = f"Belge düzgün tespit edildi (kaplama: %{coverage:.0f})."
        else:
            message = f"Belge tespit edildi ancak tam dörtgen değil (kaplama: %{coverage:.0f}). Belgeyi düz tutun."
        score_penalty = 0 if is_rectangular else 5
        document_visible = True
    else:
        message = f"Belge kısmen görünüyor (kaplama: %{coverage:.0f}). Belgenin tamamını çerçeveye alın."
        score_penalty = 10
        document_visible = True

    return {
        "edges_detected": True,
        "document_visible": document_visible,
        "is_rectangular": is_rectangular,
        "coverage_percent": round(coverage, 1),
        "corner_count": len(approx),
        "message": message,
        "score_penalty": score_penalty,
    }


def check_skew(img: object) -> dict:
    """Eğiklik/rotasyon tespiti"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)

    # Hough Line Transform ile çizgileri bul
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=100, maxLineGap=10)

    if lines is None or len(lines) == 0:
        return {
            "skew_detected": False,
            "skew_angle": 0,
            "message": "Eğiklik analizi yapılamadı.",
            "score_penalty": 0,
        }

    # Çizgilerin açılarını hesapla
    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        if x2 - x1 == 0:
            continue
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        # Yataya yakın çizgileri filtrele (-45 ile 45 derece arası)
        if -45 < angle < 45:
            angles.append(angle)

    if not angles:
        return {
            "skew_detected": False,
            "skew_angle": 0,
            "message": "Eğiklik tespit edilemedi.",
            "score_penalty": 0,
        }

    median_angle = float(np.median(angles))

    if abs(median_angle) < 2:
        message = "Belge düzgün konumlandırılmış."
        score_penalty = 0
        skew_detected = False
    elif abs(median_angle) < 5:
        message = f"Belge hafif eğik ({median_angle:.1f}°). OCR sonuçlarını etkilemez."
        score_penalty = 3
        skew_detected = True
    elif abs(median_angle) < 15:
        message = f"Belge eğik ({median_angle:.1f}°). Düzgün konumlandırmaya çalışın."
        score_penalty = 10
        skew_detected = True
    else:
        message = f"Belge çok eğik ({median_angle:.1f}°). Lütfen belgeyi düz tutun."
        score_penalty = 20
        skew_detected = True

    return {
        "skew_detected": skew_detected,
        "skew_angle": round(median_angle, 1),
        "message": message,
        "score_penalty": score_penalty,
    }


def get_enhancement_recommendations(checks: dict) -> list:
    """Otomatik iyileştirme önerileri"""
    recommendations = []

    blur = checks.get("blur", {})
    brightness = checks.get("brightness", {})
    contrast = checks.get("contrast", {})
    glare = checks.get("glare", {})
    edges = checks.get("document_edges", {})
    skew = checks.get("skew", {})

    # Öncelik sırasına göre öneriler
    if blur.get("blur_level") in ("very_blurry", "blurry"):
        recommendations.append({
            "type": "blur",
            "priority": "high",
            "title": "Netlik Düşük",
            "action": "Kamerayı sabit tutun ve odaklanmasını bekleyin",
            "icon": "focus",
        })

    if brightness.get("brightness_level") in ("very_dark", "dark"):
        recommendations.append({
            "type": "brightness",
            "priority": "high",
            "title": "Karanlık Görüntü",
            "action": "Daha aydınlık ortamda çekin veya flaş kullanın",
            "icon": "sun",
        })

    if brightness.get("brightness_level") == "overexposed":
        recommendations.append({
            "type": "brightness",
            "priority": "high",
            "title": "Aşırı Parlak",
            "action": "Flaşı kapatın veya ışık kaynağından uzaklaşın",
            "icon": "sun-dim",
        })

    if glare.get("glare_level") in ("severe", "moderate"):
        recommendations.append({
            "type": "glare",
            "priority": "high" if glare["glare_level"] == "severe" else "medium",
            "title": "Parlama Tespit Edildi",
            "action": "Flaşı kapatın, belgeyi eğin veya açıyı değiştirin",
            "icon": "sparkles",
        })

    if contrast.get("contrast_level") == "low":
        recommendations.append({
            "type": "contrast",
            "priority": "medium",
            "title": "Düşük Kontrast",
            "action": "Belgeyi koyu bir yüzeye yerleştirin",
            "icon": "contrast",
        })

    if edges.get("coverage_percent", 100) < 30:
        recommendations.append({
            "type": "framing",
            "priority": "high",
            "title": "Belge Çok Küçük",
            "action": "Belgeye daha yakın tutun",
            "icon": "maximize",
        })

    if skew.get("skew_detected") and abs(skew.get("skew_angle", 0)) > 5:
        recommendations.append({
            "type": "skew",
            "priority": "medium",
            "title": "Belge Eğik",
            "action": "Belgeyi düz bir yüzeye yerleştirin",
            "icon": "rotate",
        })

    return recommendations


def preprocess_image_for_ocr(image_base64: str) -> Optional[str]:
    """OCR için görüntü ön işleme (kontrast artırma, gürültü azaltma)"""
    if not CV2_AVAILABLE:
        return None

    img = decode_base64_image(image_base64)
    if img is None:
        return None

    try:
        # Griye çevir
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Gürültü azaltma
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)

        # Adaptive threshold ile kontrast artırma
        # CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)

        # Encode back to base64
        _, buffer = cv2.imencode('.png', enhanced)
        enhanced_base64 = base64.b64encode(buffer).decode('utf-8')
        return enhanced_base64
    except Exception:
        return None


def convert_numpy_types(obj):
    """Convert numpy types to native Python types for JSON serialization"""
    if hasattr(obj, 'dtype'):  # numpy scalar
        return obj.item()
    elif isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(v) for v in obj]
    else:
        return obj

def assess_image_quality(image_base64: str) -> dict:
    """Tam görüntü kalite değerlendirmesi (geliştirilmiş)"""
    if not CV2_AVAILABLE:
        return {
            "quality_checked": False,
            "overall_quality": "unknown",
            "overall_score": 0,
            "warnings": ["OpenCV yüklü değil, görüntü kalite kontrolü yapılamadı."],
            "checks": {},
            "recommendations": [],
        }

    img = decode_base64_image(image_base64)
    if img is None:
        return {
            "quality_checked": False,
            "overall_quality": "invalid",
            "overall_score": 0,
            "warnings": ["Görüntü dosyası okunamadı. Lütfen geçerli bir fotoğraf gönderin."],
            "checks": {},
            "recommendations": [],
        }

    try:
        # Tüm kontrolleri yap
        blur = check_blur(img)
        brightness = check_brightness(img)
        resolution = check_resolution(img)
        contrast = check_contrast(img)
        glare = check_glare(img)
        edges = check_document_edges(img)
        skew = check_skew(img)

        checks = {
            "blur": blur,
            "brightness": brightness,
            "resolution": resolution,
            "contrast": contrast,
            "glare": glare,
            "document_edges": edges,
            "skew": skew,
        }

        # Ağırlıklı puanlama
        total_penalty = sum(c.get("score_penalty", 0) for c in checks.values())
        score = max(0, 100 - total_penalty)

        # Uyarıları topla
        warnings = []
        for check_name, check_result in checks.items():
            if check_result.get("score_penalty", 0) > 0:
                warnings.append(check_result["message"])

        # İyileştirme önerileri
        recommendations = get_enhancement_recommendations(checks)

        # Genel kalite
        if score >= 80:
            overall = "good"
        elif score >= 50:
            overall = "acceptable"
        else:
            overall = "poor"

        # Provider önerisi
        if score >= 80:
            suggested_provider = "gpt-4o-mini"
            provider_reason = "Yüksek kaliteli görüntü - hızlı/ucuz provider yeterli"
        elif score >= 50:
            suggested_provider = "gpt-4o"
            provider_reason = "Orta kaliteli görüntü - yüksek doğruluklu provider önerilir"
        else:
            suggested_provider = "gpt-4o"
            provider_reason = "Düşük kaliteli görüntü - en iyi provider gerekli"

        result = {
            "quality_checked": True,
            "overall_quality": overall,
            "overall_score": score,
            "pass": score >= 40,
            "warnings": warnings,
            "checks": checks,
            "recommendations": recommendations,
            "suggested_provider": suggested_provider,
            "provider_reason": provider_reason,
            "can_enhance": score < 80,
        }

        # Convert numpy types to native Python types
        return convert_numpy_types(result)
        
    except Exception as e:
        # Return error-safe result if image processing fails
        return {
            "quality_checked": False,
            "overall_quality": "error",
            "overall_score": 0,
            "warnings": [f"Görüntü kalite kontrolü hatası: {str(e)}"],
            "checks": {},
            "recommendations": [],
            "suggested_provider": "gpt-4o",
            "provider_reason": "Kalite kontrol hatası - güvenli seçim",
            "can_enhance": False,
        }
