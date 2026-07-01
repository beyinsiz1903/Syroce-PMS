"""Pydantic request/response models + shared constants for Quick-ID."""
from typing import Optional, List
from pydantic import BaseModel, Field

# Maximum image size: ~10MB base64 (approx 7.5MB raw)
MAX_IMAGE_BASE64_LENGTH = 10 * 1024 * 1024  # 10MB

# System prompt for ID extraction (kept here so router/helper share the same text)
ID_EXTRACTION_PROMPT = """You are an expert ID document reader for a hotel check-in system. You analyze images of identity documents (ID cards, passports, driver's licenses) and extract structured information.

CRITICAL: The image may contain ONE or MULTIPLE identity documents. You MUST detect and extract data from ALL visible documents separately.

IMPORTANT RULES:
1. Count ALL visible identity documents in the image
2. Extract ALL visible text fields from EACH document separately
3. Return ONLY valid JSON - no markdown, no extra text, no code blocks
4. If a field is not visible or unclear, set it to null
5. Normalize dates to YYYY-MM-DD format
6. For gender, use "M" (Male/Erkek) or "F" (Female/Kadin)
7. Detect the document type automatically for each document
8. If the image is blurry, cropped, or not an ID document, set "is_valid" to false
9. For Turkish ID cards (TC Kimlik), extract TC Kimlik No
10. For passports, extract passport number and MRZ data if visible
11. For driver's licenses, extract license number

ALWAYS return a JSON object with a "documents" array. Even if there is only 1 document, wrap it in the array.

Return this exact JSON structure (no markdown, no code fences):
{
    "document_count": 1 or 2 or more,
    "documents": [
        {
            "is_valid": true or false,
            "document_type": "tc_kimlik" | "passport" | "drivers_license" | "old_nufus_cuzdani" | "other",
            "first_name": "string or null",
            "last_name": "string or null",
            "id_number": "string or null",
            "birth_date": "YYYY-MM-DD or null",
            "gender": "M" | "F" | null,
            "nationality": "string or null",
            "expiry_date": "YYYY-MM-DD or null",
            "document_number": "string or null",
            "birth_place": "string or null",
            "issue_date": "YYYY-MM-DD or null",
            "mother_name": "string or null",
            "father_name": "string or null",
            "address": "string or null",
            "warnings": ["list of any issues or uncertain fields"],
            "raw_extracted_text": "all visible text from this specific document"
        }
    ]
}"""


class ScanRequest(BaseModel):
    image_base64: str
    provider: Optional[str] = None  # gpt-4o, gpt-4o-mini, gemini-flash, tesseract, auto
    smart_mode: Optional[bool] = True


class GuestCreate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    id_number: Optional[str] = None
    birth_date: Optional[str] = None
    gender: Optional[str] = None
    nationality: Optional[str] = None
    document_type: Optional[str] = None
    document_number: Optional[str] = None
    birth_place: Optional[str] = None
    expiry_date: Optional[str] = None
    issue_date: Optional[str] = None
    mother_name: Optional[str] = None
    father_name: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    scan_id: Optional[str] = None
    original_extracted_data: Optional[dict] = None
    force_create: Optional[bool] = False
    kvkk_consent: Optional[bool] = False


class GuestUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    id_number: Optional[str] = None
    birth_date: Optional[str] = None
    gender: Optional[str] = None
    nationality: Optional[str] = None
    document_type: Optional[str] = None
    document_number: Optional[str] = None
    birth_place: Optional[str] = None
    expiry_date: Optional[str] = None
    issue_date: Optional[str] = None
    mother_name: Optional[str] = None
    father_name: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    role: str = "reception"


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class PasswordChange(BaseModel):
    current_password: Optional[str] = None
    new_password: str


class SettingsUpdate(BaseModel):
    retention_days_scans: Optional[int] = None
    retention_days_audit: Optional[int] = None
    store_scan_images: Optional[bool] = None
    kvkk_consent_required: Optional[bool] = None
    kvkk_consent_text: Optional[str] = None
    data_processing_purpose: Optional[str] = None
    auto_cleanup_enabled: Optional[bool] = None


class RightsRequestCreate(BaseModel):
    request_type: str
    guest_id: Optional[str] = None
    requester_name: str
    requester_email: str
    requester_id_number: Optional[str] = None
    description: str


class RightsRequestProcess(BaseModel):
    status: str
    response_note: str
    response_data: Optional[dict] = None


class FaceCompareRequest(BaseModel):
    document_image_base64: str
    selfie_image_base64: str


class LivenessCheckRequest(BaseModel):
    image_base64: str
    challenge_id: str
    session_id: str


class TcKimlikValidateRequest(BaseModel):
    tc_no: str


class EmniyetBildirimiRequest(BaseModel):
    guest_id: str


class PropertyCreate(BaseModel):
    name: str
    address: Optional[str] = ""
    phone: Optional[str] = ""
    tax_no: Optional[str] = ""
    city: Optional[str] = ""


class PropertyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    tax_no: Optional[str] = None
    city: Optional[str] = None
    is_active: Optional[bool] = None
    settings: Optional[dict] = None


class KioskSessionCreate(BaseModel):
    property_id: str
    kiosk_name: Optional[str] = "Lobby Kiosk"


class PreCheckinCreate(BaseModel):
    property_id: str
    reservation_ref: Optional[str] = ""
    guest_name: Optional[str] = ""


class PreCheckinScanRequest(BaseModel):
    image_base64: str
    kvkk_consent: Optional[bool] = False


class OfflineSyncRequest(BaseModel):
    property_id: str
    data_type: str
    data: list
    device_id: Optional[str] = None


class RoomCreate(BaseModel):
    room_number: str
    room_type: str = "standard"
    floor: int = 1
    capacity: int = 2
    property_id: Optional[str] = "default"
    features: Optional[list] = []


class RoomUpdate(BaseModel):
    room_type: Optional[str] = None
    floor: Optional[int] = None
    capacity: Optional[int] = None
    status: Optional[str] = None
    features: Optional[list] = None


class RoomAssignRequest(BaseModel):
    room_id: str
    guest_id: str


class AutoAssignRequest(BaseModel):
    guest_id: str
    property_id: Optional[str] = None
    preferred_type: Optional[str] = None


class GroupCheckinRequest(BaseModel):
    guest_ids: List[str]
    room_id: Optional[str] = None


class GuestPhotoRequest(BaseModel):
    # v50 (Bug CK): minimal length to reject empty / "AAAA" trivial payloads.
    image_base64: str = Field(..., min_length=128, max_length=MAX_IMAGE_BASE64_LENGTH)


class BackupCreateRequest(BaseModel):
    description: Optional[str] = ""


class BackupRestoreRequest(BaseModel):
    backup_id: str
