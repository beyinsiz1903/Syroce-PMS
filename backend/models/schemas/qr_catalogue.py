import re
from datetime import datetime
from enum import Enum
from typing import Any, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CODE_REGEX = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")
ICON_REGEX = re.compile(r"^[a-z0-9_-]+$")
TIME_REGEX = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
LANG_REGEX = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")


class CatalogueMode(str, Enum):
    default = "default"
    configured = "configured"
    disabled = "disabled"


class InputType(str, Enum):
    one_tap = "one_tap"
    quantity = "quantity"
    single_choice = "single_choice"
    multi_choice = "multi_choice"
    date = "date"
    time = "time"
    datetime = "datetime"


class AutoPriority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


def validate_multilingual_dict(v: dict[str, str], max_len: int = 100) -> dict[str, str]:
    if not v:
        raise ValueError("Labels cannot be empty")
    for lang, text in v.items():
        if not LANG_REGEX.match(lang):
            raise ValueError(f"Invalid language code: {lang}")
        clean_text = text.strip()
        if not clean_text:
            raise ValueError(f"Text for {lang} cannot be empty")
        if len(clean_text) > max_len:
            raise ValueError(f"Text for {lang} is too long (max {max_len})")
        v[lang] = clean_text
    return v


class GuestServiceCatalogueSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    property_id: str
    mode: CatalogueMode = CatalogueMode.default


class GuestServiceDepartment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    property_id: str
    department_code: str
    labels: dict[str, str]
    icon: str
    enabled: bool = True
    display_order: int = 0
    created_at: datetime
    updated_at: datetime
    version: int = 1

    @field_validator("department_code")
    @classmethod
    def validate_code(cls, v):
        if not CODE_REGEX.match(v):
            raise ValueError("Invalid department_code format")
        return v

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, v):
        if not ICON_REGEX.match(v):
            raise ValueError("Invalid icon format")
        return v

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, v):
        return validate_multilingual_dict(v, max_len=100)


class QuantityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min: int = 1
    max: int = 10
    default: int = 1

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.min < 1:
            raise ValueError("min must be >= 1")
        if self.max < self.min:
            raise ValueError("max must be >= min")
        if self.max > 20:
            raise ValueError("max exceeds reasonable upper bound of 20")
        if not (self.min <= self.default <= self.max):
            raise ValueError("default must be within min and max bounds")
        return self


class ChoiceOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    labels: dict[str, str]

    @field_validator("code")
    @classmethod
    def validate_code(cls, v):
        if not CODE_REGEX.match(v):
            raise ValueError("Invalid choice option code")
        return v

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, v):
        return validate_multilingual_dict(v, max_len=100)


class ChoiceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    options: list[ChoiceOption]
    min_selections: int = 1
    max_selections: int = 1

    @field_validator("options")
    @classmethod
    def validate_options(cls, v):
        if not v:
            raise ValueError("Options cannot be empty")
        codes = [opt.code for opt in v]
        if len(codes) != len(set(codes)):
            raise ValueError("Option codes must be unique")
        return v

    @model_validator(mode="after")
    def validate_selections(self):
        if self.min_selections < 0:
            raise ValueError("min_selections must be >= 0")
        if self.max_selections < 1:
            raise ValueError("max_selections must be >= 1")
        if self.min_selections > self.max_selections:
            raise ValueError("min_selections cannot exceed max_selections")
        if self.max_selections > len(self.options):
            raise ValueError("max_selections cannot exceed the number of options")
        return self


class DateConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_days_ahead: int = 0
    max_days_ahead: int = 30

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.min_days_ahead < 0:
            raise ValueError("min_days_ahead must be >= 0")
        if self.max_days_ahead > 365:
            raise ValueError("max_days_ahead must be <= 365")
        if self.min_days_ahead > self.max_days_ahead:
            raise ValueError("min_days_ahead cannot exceed max_days_ahead")
        return self


class TimeConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interval_minutes: int = 15

    @field_validator("interval_minutes")
    @classmethod
    def validate_interval(cls, v):
        if v < 5 or v > 60:
            raise ValueError("interval_minutes must be between 5 and 60")
        if 60 % v != 0:
            raise ValueError("60 must be divisible by interval_minutes")
        return v

class DateTimeConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_days_ahead: int = 0
    max_days_ahead: int = 30
    interval_minutes: int = 15

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.min_days_ahead < 0:
            raise ValueError("min_days_ahead must be >= 0")
        if self.max_days_ahead > 365:
            raise ValueError("max_days_ahead must be <= 365")
        if self.min_days_ahead > self.max_days_ahead:
            raise ValueError("min_days_ahead cannot exceed max_days_ahead")
        if self.interval_minutes < 5 or self.interval_minutes > 60:
            raise ValueError("interval_minutes must be between 5 and 60")
        if 60 % self.interval_minutes != 0:
            raise ValueError("60 must be divisible by interval_minutes")
        return self


class EmptyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServiceHoursConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls, v):
        if not TIME_REGEX.match(v):
            raise ValueError("Invalid time format, must be HH:MM")
        return v


class GuestServiceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    property_id: str
    service_code: str
    department_code: str
    labels: dict[str, str]
    description: dict[str, str] | None = None
    icon: str
    input_type: InputType
    input_config: Union[QuantityConfig, ChoiceConfig, DateConstraints, TimeConstraints, DateTimeConstraints, EmptyConfig] = Field(default_factory=EmptyConfig)
    auto_priority: AutoPriority = AutoPriority.normal
    estimated_minutes: int = 0
    is_chargeable: bool = False
    charge_warning: dict[str, str] | None = None
    service_hours: ServiceHoursConfig | None = None
    enabled: bool = True
    display_order: int = 0
    created_at: datetime
    updated_at: datetime
    version: int = 1

    @field_validator("service_code", "department_code")
    @classmethod
    def validate_codes(cls, v):
        if not CODE_REGEX.match(v):
            raise ValueError("Invalid code format")
        return v

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, v):
        if not ICON_REGEX.match(v):
            raise ValueError("Invalid icon format")
        return v

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, v):
        return validate_multilingual_dict(v, max_len=100)

    @field_validator("description", "charge_warning")
    @classmethod
    def validate_optional_dict(cls, v):
        if v is not None:
            return validate_multilingual_dict(v, max_len=500)
        return v

    @field_validator("estimated_minutes")
    @classmethod
    def validate_estimated_minutes(cls, v):
        if v < 0 or v > 1440:
            raise ValueError("estimated_minutes must be between 0 and 1440")
        return v

    @model_validator(mode="before")
    @classmethod
    def pre_validate_config(cls, data: Any):
        if isinstance(data, dict):
            input_type = data.get("input_type")
            config = data.get("input_config", {})
            if isinstance(config, dict):
                if input_type == InputType.one_tap:
                    data["input_config"] = EmptyConfig.model_validate(config)
                elif input_type == InputType.quantity:
                    data["input_config"] = QuantityConfig.model_validate(config)
                elif input_type in (InputType.single_choice, InputType.multi_choice):
                    data["input_config"] = ChoiceConfig.model_validate(config)
                elif input_type == InputType.date:
                    data["input_config"] = DateConstraints.model_validate(config)
                elif input_type == InputType.time:
                    data["input_config"] = TimeConstraints.model_validate(config)
                elif input_type == InputType.datetime:
                    data["input_config"] = DateTimeConstraints.model_validate(config)
        return data

    @model_validator(mode="after")
    def validate_input_config(self):
        input_type = self.input_type
        config = self.input_config

        if input_type == InputType.one_tap:
            if not isinstance(config, EmptyConfig):
                raise ValueError("one_tap requires EmptyConfig")
        elif input_type == InputType.quantity:
            if not isinstance(config, QuantityConfig):
                raise ValueError("quantity requires QuantityConfig")
        elif input_type in (InputType.single_choice, InputType.multi_choice):
            if not isinstance(config, ChoiceConfig):
                raise ValueError("choice requires ChoiceConfig")
            if input_type == InputType.single_choice:
                if config.max_selections != 1:
                    raise ValueError("single_choice must have max_selections = 1")
                if config.min_selections not in (0, 1):
                    raise ValueError("single_choice min_selections must be 0 or 1")
        elif input_type == InputType.date:
            if not isinstance(config, DateConstraints):
                raise ValueError("date requires DateConstraints")
        elif input_type == InputType.time:
            if not isinstance(config, TimeConstraints):
                raise ValueError("time requires TimeConstraints")
        elif input_type == InputType.datetime:
            if not isinstance(config, DateTimeConstraints):
                raise ValueError("datetime requires DateTimeConstraints")

        return self
