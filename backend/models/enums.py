"""
Syroce PMS - Enum Definitions
All enum types used across the application.
Extracted from server.py for modularity.
"""
from enum import Enum

# ============= ENUMS =============

class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"  # Platform admin - can manage all hotels
    ADMIN = "admin"  # Full access - Owner/IT (single hotel)
    SUPERVISOR = "supervisor"  # Management oversight
    FRONT_DESK = "front_desk"  # Reservations, check-in/out
    HOUSEKEEPING = "housekeeping"  # Room status, tasks
    SALES = "sales"  # Corporate accounts, contracts
    FINANCE = "finance"  # Accounting, invoices, AR
    PROCUREMENT = "procurement"  # Suppliers, purchase orders, goods receipt
    STAFF = "staff"  # Limited access
    GUEST = "guest"  # Guest portal
    AGENCY_ADMIN = "agency_admin"  # Agency admin - can manage agency
    AGENCY_AGENT = "agency_agent"  # Agency staff - can create requests
    CALL_CENTER_AGENT = "call_center_agent"  # Çağrı merkezi temsilcisi (Contact Center)

class Permission(str, Enum):
    # Booking permissions
    VIEW_BOOKINGS = "view_bookings"
    CREATE_BOOKING = "create_booking"
    EDIT_BOOKING = "edit_booking"
    DELETE_BOOKING = "delete_booking"
    CHECKIN = "checkin"
    CHECKOUT = "checkout"

    # Folio permissions
    VIEW_FOLIO = "view_folio"
    POST_CHARGE = "post_charge"
    POST_PAYMENT = "post_payment"
    VOID_CHARGE = "void_charge"
    TRANSFER_FOLIO = "transfer_folio"
    CLOSE_FOLIO = "close_folio"
    OVERRIDE_RATE = "override_rate"

    # Company permissions
    VIEW_COMPANIES = "view_companies"
    CREATE_COMPANY = "create_company"
    EDIT_COMPANY = "edit_company"

    # Housekeeping permissions
    VIEW_HK_BOARD = "view_hk_board"
    UPDATE_ROOM_STATUS = "update_room_status"
    ASSIGN_TASK = "assign_task"

    # Reports permissions
    VIEW_REPORTS = "view_reports"
    VIEW_FINANCIAL_REPORTS = "view_financial_reports"
    EXPORT_DATA = "export_data"

    # Admin permissions
    MANAGE_USERS = "manage_users"
    MANAGE_ROOMS = "manage_rooms"
    SYSTEM_SETTINGS = "system_settings"

    # Internal messaging permissions
    SEND_URGENT_MESSAGE = "send_urgent_message"

    # Audit / compliance permissions
    # Manager-only access to audit-derived reports (e.g. urgent message report).
    VIEW_AUDIT_LOG = "view_audit_log"

    # HR module permissions (v2 Foundation, Task #262).
    # VIEW_HR: personel listesi + profil + master data okuma (HR Admin, HR Manager,
    #   Department Manager scope-filtered, super_admin/admin).
    # MANAGE_HR: master data CRUD, personel CRUD, departman/pozisyon değişiklikleri,
    #   PII tam görünürlük (TC/IBAN/maaş unmasked).
    # Geriye-uyumluluk: `view_executive_reports` op key'i hâlâ HR yüzeylerine
    # erişim sağlar (alias) — eski deploy'larda kayıtlı `view_financial_reports`
    # perm'iyle bordro/maaş raporu açılır; bu yeni perm'ler üstüne kurulur,
    # mevcut akışları bozmaz.
    VIEW_HR = "view_hr"
    MANAGE_HR = "manage_hr"

    # Contact Center (omnichannel) permissions
    # VIEW: konuşma/mesaj listesini görüntüleme; MANAGE: atama/yanıt/durum değişimi.
    VIEW_CONTACT_CENTER = "view_contact_center"
    MANAGE_CONTACT_CENTER = "manage_contact_center"

class RoomStatus(str, Enum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    DIRTY = "dirty"
    CLEANING = "cleaning"
    INSPECTED = "inspected"
    MAINTENANCE = "maintenance"
    OUT_OF_ORDER = "out_of_order"

class BookingStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    GUARANTEED = "guaranteed"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"

class PaymentStatus(str, Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"
    REFUNDED = "refunded"

class PaymentMethod(str, Enum):
    CASH = "cash"
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    ONLINE = "online"

class ChargeType(str, Enum):
    ROOM = "room"

class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"

class LoyaltyTier(str, Enum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"

class RoomServiceStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class ChannelType(str, Enum):
    DIRECT = "direct"
    BOOKING_COM = "booking_com"
    EXPEDIA = "expedia"
    AIRBNB = "airbnb"
    AGODA = "agoda"
    OWN_WEBSITE = "own_website"
    HOTELS_COM = "hotels_com"
    TRIP_ADVISOR = "trip_advisor"

class ChannelStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    SYNCING = "syncing"

class ChannelHealth(str, Enum):
    HEALTHY = "healthy"
    DELAYED = "delayed"
    ERROR = "error"
    OFFLINE = "offline"

class MappingStatus(str, Enum):
    MAPPED = "mapped"
    UNMAPPED = "unmapped"
    CONFLICT = "conflict"
    NEEDS_REVIEW = "needs_review"

class PricingStrategy(str, Enum):
    STATIC = "static"
    DYNAMIC = "dynamic"
    COMPETITIVE = "competitive"
    OCCUPANCY_BASED = "occupancy_based"

class ContractedRateType(str, Enum):
    CORP_STD = "corp_std"  # Standard Corporate
    CORP_PREF = "corp_pref"  # Preferred Corporate
    GOV = "gov"  # Government Rate
    TA = "ta"  # Travel Agent Rate
    CREW = "crew"  # Airline Crew Rate
    MICE = "mice"  # Event/Conference Rate
    LTS = "lts"  # Long Stay/Project Rate
    TOU = "tou"  # Tour Operator/Series Group Rate

class RateType(str, Enum):
    STANDARD = "standard"  # Standard Rate
    BAR = "bar"  # Best Available Rate / Rack Rate
    CORPORATE = "corporate"
    GOVERNMENT = "government"
    WHOLESALE = "wholesale"
    PACKAGE = "package"
    PROMOTIONAL = "promotional"
    NON_REFUNDABLE = "non_refundable"
    LONG_STAY = "long_stay"
    DAY_USE = "day_use"

class MarketSegment(str, Enum):
    CORPORATE = "corporate"
    LEISURE = "leisure"
    GROUP = "group"
    MICE = "mice"
    GOVERNMENT = "government"
    CREW = "crew"
    WHOLESALE = "wholesale"
    LONG_STAY = "long_stay"
    COMPLIMENTARY = "complimentary"
    OTHER = "other"

class CancellationPolicyType(str, Enum):
    SAME_DAY = "same_day"  # Free cancellation until 18:00
    H24 = "h24"  # 24 hours before check-in
    H48 = "h48"  # 48 hours before check-in
    H72 = "h72"  # 72 hours before check-in
    D7 = "d7"  # 7 days before check-in
    D14 = "d14"  # 14 days before check-in
    NON_REFUNDABLE = "non_refundable"
    FLEXIBLE = "flexible"
    SPECIAL_EVENT = "special_event"

class CompanyStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"  # Quick-created from booking form
    INACTIVE = "inactive"

class OTAChannel(str, Enum):
    BOOKING_COM = "booking_com"
    EXPEDIA = "expedia"
    AIRBNB = "airbnb"
    AGODA = "agoda"
    HOTELS_COM = "hotels_com"
    DIRECT = "direct"  # Direct booking
    PHONE = "phone"  # Phone booking
    WALK_IN = "walk_in"

class OTAPaymentModel(str, Enum):
    AGENCY = "agency"  # OTA collects, pays hotel
    HOTEL_COLLECT = "hotel_collect"  # Hotel collects from guest
    VIRTUAL_CARD = "virtual_card"  # OTA provides virtual card
    PREPAID = "prepaid"  # Guest prepaid to OTA

class ParityStatus(str, Enum):
    NEGATIVE = "negative"  # OTA cheaper (bad)
    POSITIVE = "positive"  # Direct cheaper (good)
    EQUAL = "equal"  # Same rate
    UNKNOWN = "unknown"

class FolioType(str, Enum):
    GUEST = "guest"
    COMPANY = "company"
    AGENCY = "agency"

class FolioStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    TRANSFERRED = "transferred"
    VOIDED = "voided"

class ChargeCategory(str, Enum):
    ROOM = "room"
    FOOD = "food"
    BEVERAGE = "beverage"
    MINIBAR = "minibar"
    SPA = "spa"
    LAUNDRY = "laundry"
    PHONE = "phone"
    INTERNET = "internet"
    PARKING = "parking"
    CITY_TAX = "city_tax"
    SERVICE_CHARGE = "service_charge"
    OTHER = "other"

class FolioOperationType(str, Enum):
    TRANSFER = "transfer"
    SPLIT = "split"
    MERGE = "merge"
    VOID = "void"
    REFUND = "refund"

class PaymentType(str, Enum):
    PREPAYMENT = "prepayment"
    DEPOSIT = "deposit"
    INTERIM = "interim"
    FINAL = "final"
    REFUND = "refund"

# Finance Mobile Enhancements - Department & Risk Management
class DepartmentType(str, Enum):
    ROOMS = "rooms"  # Konaklama
    FNB = "fnb"  # Restaurant, Bar, Room Service
    SPA = "spa"  # SPA & Wellness
    LAUNDRY = "laundry"  # Laundry / Dry Cleaning
    MINIBAR = "minibar"  # Mini Bar
    TELEPHONE = "telephone"  # Telephone / Communication
    TRANSPORTATION = "transportation"  # VIP Transfer
    TECHNICAL = "technical"  # Technical Charges
    HOUSEKEEPING_CHARGES = "housekeeping_charges"  # Lost&Found Compensation
    OTHER = "other"  # Other Services

class RiskLevel(str, Enum):
    NORMAL = "normal"  # 0-7 days - Green
    WARNING = "warning"  # 8-14 days - Yellow
    CRITICAL = "critical"  # 15-30 days - Red
    SUSPICIOUS = "suspicious"  # 30+ days - Black



# Maintenance & Technical Service Enums
class MaintenanceTaskStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    WAITING_PARTS = "waiting_parts"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class MaintenancePriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"
    EMERGENCY = "emergency"

class WarehouseLocation(str, Enum):
    MAIN_WAREHOUSE = "main_warehouse"
    FLOOR_STORAGE = "floor_storage"
    WORKSHOP = "workshop"
    EXTERNAL = "external"

class MaintenanceType(str, Enum):
    CORRECTIVE = "corrective"  # Arıza onarımı
    PREVENTIVE = "preventive"  # Önleyici bakım
    PLANNED = "planned"  # Planlı bakım
    EMERGENCY = "emergency"  # Acil müdahale


# F&B Management Enums
class OrderStatus(str, Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    READY = "ready"
    SERVED = "served"
    CANCELLED = "cancelled"

class OutletType(str, Enum):
    RESTAURANT = "restaurant"
    BAR = "bar"
    ROOM_SERVICE = "room_service"
    CAFE = "cafe"
    POOLSIDE = "poolside"
    BANQUET = "banquet"

class MeasurementUnit(str, Enum):
    KG = "kg"
    GRAM = "gram"
    LITER = "liter"
    ML = "ml"
    PIECE = "piece"
    PORTION = "portion"


# Front Office Mobile Enums
class GuestRequestType(str, Enum):
    EXTRA_TOWEL = "extra_towel"
    EXTRA_PILLOW = "extra_pillow"
    ROOM_CLEANING = "room_cleaning"
    WAKE_UP_CALL = "wake_up_call"
    TAXI = "taxi"
    RESTAURANT_RESERVATION = "restaurant_reservation"
    LATE_CHECKOUT = "late_checkout"
    EARLY_CHECKIN = "early_checkin"
    MAINTENANCE = "maintenance"
    OTHER = "other"

class GuestRequestStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class CheckInStatus(str, Enum):
    PRE_ARRIVAL = "pre_arrival"
    CHECKING_IN = "checking_in"
    CHECKED_IN = "checked_in"
    IN_HOUSE = "in_house"


# Housekeeping Enhanced Enums
class InspectionStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class LostFoundStatus(str, Enum):
    FOUND = "found"
    IN_STORAGE = "in_storage"
    CLAIMED = "claimed"


# Revenue Management Enums (MarketSegment duplicate removed — using first definition above)

# Duplicate PricingStrategy enum removed - using the first one





# ── Contact Center (omnichannel) enums ──

class ContactCenterChannel(str, Enum):
    WHATSAPP = "whatsapp"
    VOICE = "voice"
    WEB = "web"
    SOCIAL = "social"
    EMAIL = "email"
    SMS = "sms"


class ConversationStatus(str, Enum):
    OPEN = "open"
    PENDING = "pending"
    ASSIGNED = "assigned"
    RESOLVED = "resolved"
    CLOSED = "closed"


class MessageDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageStatus(str, Enum):
    RECEIVED = "received"
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class CallStatus(str, Enum):
    RINGING = "ringing"
    ANSWERED = "answered"
    MISSED = "missed"
    COMPLETED = "completed"
    FAILED = "failed"


# Role-Permission Mapping
ROLE_PERMISSIONS = {
    UserRole.ADMIN: [p.value for p in Permission],  # All permissions
    UserRole.SUPERVISOR: [
        Permission.VIEW_BOOKINGS, Permission.CREATE_BOOKING, Permission.EDIT_BOOKING,
        Permission.CHECKIN, Permission.CHECKOUT,
        Permission.VIEW_FOLIO, Permission.POST_CHARGE, Permission.POST_PAYMENT,
        Permission.OVERRIDE_RATE, Permission.CLOSE_FOLIO,
        Permission.VIEW_COMPANIES, Permission.EDIT_COMPANY,
        Permission.VIEW_HK_BOARD, Permission.UPDATE_ROOM_STATUS, Permission.ASSIGN_TASK,
        Permission.VIEW_REPORTS, Permission.VIEW_FINANCIAL_REPORTS,
        Permission.SEND_URGENT_MESSAGE,
        Permission.VIEW_AUDIT_LOG,
        # v2 HR: supervisor düzeyi HR okuma + master data yönetimi yapabilir.
        Permission.VIEW_HR, Permission.MANAGE_HR,
        # Contact Center: supervisor konuşmaları görür ve yönetir.
        Permission.VIEW_CONTACT_CENTER, Permission.MANAGE_CONTACT_CENTER,
    ],
    UserRole.FRONT_DESK: [
        Permission.VIEW_BOOKINGS, Permission.CREATE_BOOKING, Permission.EDIT_BOOKING,
        Permission.CHECKIN, Permission.CHECKOUT,
        Permission.VIEW_FOLIO, Permission.POST_CHARGE, Permission.POST_PAYMENT,
        Permission.VIEW_COMPANIES,
        Permission.VIEW_HK_BOARD,
        Permission.VIEW_REPORTS,
        # Contact Center: resepsiyon (receptionist) küçük otellerde
        # konuşmaları görür ve yönetir.
        Permission.VIEW_CONTACT_CENTER, Permission.MANAGE_CONTACT_CENTER,
    ],
    UserRole.HOUSEKEEPING: [
        Permission.VIEW_BOOKINGS,
        Permission.VIEW_HK_BOARD, Permission.UPDATE_ROOM_STATUS, Permission.ASSIGN_TASK
    ],
    UserRole.SALES: [
        Permission.VIEW_BOOKINGS, Permission.CREATE_BOOKING,
        Permission.VIEW_COMPANIES, Permission.CREATE_COMPANY, Permission.EDIT_COMPANY,
        Permission.VIEW_REPORTS
    ],
    UserRole.FINANCE: [
        Permission.VIEW_BOOKINGS,
        Permission.VIEW_FOLIO, Permission.POST_CHARGE, Permission.POST_PAYMENT,
        Permission.VOID_CHARGE, Permission.CLOSE_FOLIO,
        Permission.VIEW_COMPANIES,
        Permission.VIEW_REPORTS, Permission.VIEW_FINANCIAL_REPORTS, Permission.EXPORT_DATA,
        # v2 HR: Finance rolü bordro/maaş raporlarını görür (VIEW_HR), ama
        # MANAGE_HR'a sahip değil — personel/dept master data CRUD kapalı.
        Permission.VIEW_HR,
    ],
    UserRole.PROCUREMENT: [
        Permission.VIEW_COMPANIES, Permission.CREATE_COMPANY, Permission.EDIT_COMPANY,
        Permission.VIEW_REPORTS, Permission.EXPORT_DATA,
    ],
    UserRole.STAFF: [
        Permission.VIEW_BOOKINGS,
        Permission.VIEW_HK_BOARD
    ],
    UserRole.CALL_CENTER_AGENT: [
        # Çağrı merkezi temsilcisi: konuşmaları görür/yönetir + rezervasyon arar.
        Permission.VIEW_BOOKINGS,
        Permission.VIEW_CONTACT_CENTER, Permission.MANAGE_CONTACT_CENTER,
    ],
}



# ── Room Block enums (moved from domains.pms.room_block_models) ──

class BlockType(str, Enum):
    OUT_OF_ORDER = "out_of_order"
    OUT_OF_SERVICE = "out_of_service"
    MAINTENANCE = "maintenance"

class BlockStatus(str, Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
