from pydantic import BaseModel, Field


class ModuleFeature(BaseModel):
    key: str
    description: str

class ModuleLimit(BaseModel):
    key: str
    description: str

class EditionDefinition(BaseModel):
    key: str
    name: str
    features: set[str] = Field(default_factory=set)
    limits: dict[str, int] = Field(default_factory=dict)

class ModuleDefinition(BaseModel):
    key: str
    name: str
    features: list[ModuleFeature] = Field(default_factory=list)
    limits: list[ModuleLimit] = Field(default_factory=list)
    editions: dict[str, EditionDefinition] = Field(default_factory=dict)

# ─── SYROCE ENTITLEMENT REGISTRY ───

ENTITLEMENT_REGISTRY: dict[str, ModuleDefinition] = {
    "hr": ModuleDefinition(
        key="hr",
        name="İnsan Kaynakları",
        features=[
            ModuleFeature(key="payroll", description="Bordro Yönetimi (Legacy)"),
            ModuleFeature(key="leave", description="İzin ve Mesai Yönetimi (Legacy)"),
            ModuleFeature(key="recruitment", description="İşe Alım ve Personel Talepleri (Legacy)"),
            ModuleFeature(key="shift", description="Vardiya Planlama (Legacy)"),
            ModuleFeature(key="advanced_scheduling", description="Gelişmiş Vardiya Planlama (Gelecek)"),
            ModuleFeature(key="leave_management", description="Gelişmiş İzin Yönetimi (Gelecek)"),
            ModuleFeature(key="performance_management", description="Performans Yönetimi"),
            ModuleFeature(key="payroll_export", description="Bordro Dışa Aktarma (Gelecek)"),
            ModuleFeature(key="advanced_hr_reporting", description="Gelişmiş İK Raporları"),
        ],
        limits=[
            ModuleLimit(key="employees", description="Maksimum Personel Sayısı (Legacy)"),
            ModuleLimit(key="active_employees", description="Aktif Çalışan Limiti"),
        ],
        editions={
            "basic": EditionDefinition(
                key="basic",
                name="HR Basic",
                features={"shift"},  # Legacy support; performance_management Basic'te yok
                limits={
                    "employees": 50,  # Legacy support
                    "active_employees": 25,
                }
            ),
            "pro": EditionDefinition(
                key="pro",
                name="HR Pro",
                features={
                    "shift", "payroll", "leave", "recruitment",  # Legacy support
                    "advanced_scheduling", "leave_management",    # Gelecek — runtime'da henüz guard yok
                    "performance_management",
                    "payroll_export",                            # Gelecek — runtime'da henüz guard yok
                    "advanced_hr_reporting",
                },
                limits={
                    "employees": 200,  # Legacy support
                    "active_employees": 250,
                }
            )
        }
    ),
    "pos_fnb": ModuleDefinition(
        key="pos_fnb",
        name="Restoran POS (F&B)",
        features=[
            ModuleFeature(key="kds", description="Mutfak Ekranı (KDS) erişimi"),
            ModuleFeature(key="inventory", description="Stok ve reçete modülü"),
            ModuleFeature(key="multi_outlet", description="Çoklu outlet/kasa desteği"),
            ModuleFeature(key="mobile_waiter", description="Mobil garson terminali"),
        ],
        limits=[
            ModuleLimit(key="outlets", description="Maksimum outlet (kasa) sayısı"),
            ModuleLimit(key="devices", description="Maksimum POS cihazı (mobil+sabit) sayısı"),
        ],
        editions={
            "basic": EditionDefinition(
                key="basic",
                name="POS Basic",
                features=set(),
                limits={
                    "outlets": 1,
                    "devices": 3,
                }
            ),
            "pro": EditionDefinition(
                key="pro",
                name="POS Pro",
                features={"kds", "inventory", "multi_outlet", "mobile_waiter"},
                limits={
                    "outlets": 5,
                    "devices": 20,
                }
            )
        }
    ),
    "mice": ModuleDefinition(
        key="mice",
        name="MICE / Banquet",
        features=[
            ModuleFeature(key="proposals_contracts", description="Teklif ve Sözleşme Yönetimi"),
            ModuleFeature(key="banquet_operations", description="BEO, Mutfak Fişi, Ops Sheet"),
            ModuleFeature(key="advanced_reporting", description="Gelişmiş MICE Raporları"),
        ],
        limits=[
            ModuleLimit(key="spaces_limit", description="Maksimum Salon Sayısı"),
            ModuleLimit(key="concurrent_events", description="Eşzamanlı Etkinlik Limiti"),
        ],
        editions={
            "basic": EditionDefinition(
                key="basic",
                name="MICE Basic",
                features=set(),
                limits={
                    "spaces_limit": 2,
                    "concurrent_events": 5,
                }
            ),
            "pro": EditionDefinition(
                key="pro",
                name="MICE Pro",
                features={"proposals_contracts", "banquet_operations", "advanced_reporting"},
                limits={
                    "spaces_limit": 10,
                    "concurrent_events": 50,
                }
            )
        }
    ),
    "housekeeping": ModuleDefinition(
        key="housekeeping",
        name="Kat Hizmetleri (Housekeeping)",
        features=[
            ModuleFeature(key="quality_control", description="Kalite Kontrol ve Denetim Görevleri"),
            ModuleFeature(key="advanced_reporting", description="Detaylı Personel Performans Raporları"),
            ModuleFeature(key="mobile_app", description="Mobil HK Uygulaması Erişimi"),
        ],
        limits=[
            ModuleLimit(key="active_tasks", description="Maksimum Aktif Görev Sayısı"),
        ],
        editions={
            "basic": EditionDefinition(
                key="basic",
                name="Housekeeping Basic",
                features=set(),
                limits={
                    "active_tasks": 100,
                }
            ),
            "pro": EditionDefinition(
                key="pro",
                name="Housekeeping Pro",
                features={"quality_control", "advanced_reporting", "mobile_app"},
                limits={
                    "active_tasks": 1000,
                }
            )
        }
    ),
    "spa": ModuleDefinition(
        key="spa",
        name="Spa & Wellness",
        features=[
            ModuleFeature(key="cross_department_packages", description="Spa & Restoran Çapraz Paketleri"),
            ModuleFeature(key="advanced_availability", description="Gelişmiş Müsaitlik ve Bekleme Listesi"),
            ModuleFeature(key="guest_history", description="Detaylı Misafir Geçmişi (CRM)"),
        ],
        limits=[
            ModuleLimit(key="therapists", description="Maksimum Terapist Sayısı"),
            ModuleLimit(key="rooms", description="Maksimum Tedavi Odası Sayısı"),
        ],
        editions={
            "basic": EditionDefinition(
                key="basic",
                name="Spa Basic",
                features=set(),
                limits={
                    "therapists": 3,
                    "rooms": 2,
                }
            ),
            "pro": EditionDefinition(
                key="pro",
                name="Spa Pro",
                features={"cross_department_packages", "advanced_availability", "guest_history"},
                limits={
                    "therapists": 20,
                    "rooms": 10,
                }
            )
        }
    ),
    "parking": ModuleDefinition(
        key="parking",
        name="Otopark & Transfer",
        features=[
            ModuleFeature(key="valet_service", description="Vale Hizmeti"),
            ModuleFeature(key="lpr_integration", description="Plaka Tanıma (LPR) Entegrasyonu"),
            ModuleFeature(key="long_term_parking", description="Uzun Dönem Park ve Personel Abonmanlıkları"),
            ModuleFeature(key="parking_analytics", description="Gelir ve Doluluk Analiz Raporları"),
        ],
        limits=[
            ModuleLimit(key="transfer_vehicles", description="Maksimum Transfer Aracı Sayısı"),
            ModuleLimit(key="parking_spots", description="Maksimum Otopark Yeri Sayısı"),
        ],
        editions={
            "basic": EditionDefinition(
                key="basic",
                name="Parking Basic",
                features=set(),
                limits={
                    "transfer_vehicles": 2,
                    "parking_spots": 50,
                }
            ),
            "pro": EditionDefinition(
                key="pro",
                name="Parking Pro",
                features={"valet_service", "lpr_integration", "long_term_parking", "parking_analytics"},
                limits={
                    "transfer_vehicles": 10,
                    "parking_spots": 500,
                }
            )
        }
    )
}

def get_module_definition(module_key: str) -> ModuleDefinition | None:
    return ENTITLEMENT_REGISTRY.get(module_key)
