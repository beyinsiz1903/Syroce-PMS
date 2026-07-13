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
    )
}

def get_module_definition(module_key: str) -> ModuleDefinition | None:
    return ENTITLEMENT_REGISTRY.get(module_key)
