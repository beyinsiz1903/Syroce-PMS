from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from datetime import datetime
import re

from pydantic import BaseModel, Field, model_validator, field_validator

CODE_REGEX = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")
ICON_REGEX = re.compile(r"^[a-z0-9_-]+$")
TIME_REGEX = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


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


class GuestServiceCatalogueSettings(BaseModel):
    tenant_id: str
    property_id: str
    mode: CatalogueMode = CatalogueMode.default


class GuestServiceDepartment(BaseModel):
    tenant_id: str
    property_id: str
    department_code: str
    labels: Dict[str, str]
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
        if not v:
            raise ValueError("Labels cannot be empty")
        return v


class QuantityConfig(BaseModel):
    min: int = 1
    max: int = 10
    default: int = 1

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.min is not None and self.max is not None:
            if self.min > self.max:
                raise ValueError("min cannot be greater than max")
            if self.default is not None and not (self.min <= self.default <= self.max):
                raise ValueError("default must be within min and max bounds")
        return self


class ChoiceOption(BaseModel):
    code: str
    labels: Dict[str, str]

    @field_validator("code")
    @classmethod
    def validate_code(cls, v):
        if not CODE_REGEX.match(v):
            raise ValueError("Invalid choice option code")
        return v


class ChoiceConfig(BaseModel):
    options: List[ChoiceOption]
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


class DateConstraints(BaseModel):
    min_days_ahead: int = 0
    max_days_ahead: int = 30


class TimeConstraints(BaseModel):
    interval_minutes: int = 15


class EmptyConfig(BaseModel):
    pass


class ServiceHoursConfig(BaseModel):
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls, v):
        if not TIME_REGEX.match(v):
            raise ValueError("Invalid time format, must be HH:MM")
        return v


class GuestServiceItem(BaseModel):
    tenant_id: str
    property_id: str
    service_code: str
    department_code: str
    labels: Dict[str, str]
    description: Optional[Dict[str, str]] = None
    icon: str
    input_type: InputType
    input_config: Union[QuantityConfig, ChoiceConfig, DateConstraints, TimeConstraints, EmptyConfig] = Field(default_factory=EmptyConfig)
    auto_priority: AutoPriority = AutoPriority.normal
    estimated_minutes: int = 0
    is_chargeable: bool = False
    charge_warning: Optional[Dict[str, str]] = None
    service_hours: Optional[ServiceHoursConfig] = None
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
        if not v:
            raise ValueError("Labels cannot be empty")
        return v

    @field_validator("estimated_minutes")
    @classmethod
    def validate_estimated_minutes(cls, v):
        if v < 0 or v > 1440:
            raise ValueError("estimated_minutes must be between 0 and 1440")
        return v

    @model_validator(mode="after")
    def validate_input_config(self):
        input_type = self.input_type
        config = self.input_config

        if input_type == InputType.one_tap:
            if not isinstance(config, EmptyConfig):
                if config == {}:
                     self.input_config = EmptyConfig()
                else:
                    raise ValueError("one_tap does not support input_config")
        elif input_type == InputType.quantity:
            if not isinstance(config, QuantityConfig):
                raise ValueError("quantity requires QuantityConfig")
        elif input_type in (InputType.single_choice, InputType.multi_choice):
            if not isinstance(config, ChoiceConfig):
                raise ValueError("choice requires ChoiceConfig")
            if input_type == InputType.single_choice and config.max_selections != 1:
                raise ValueError("single_choice must have max_selections = 1")
        elif input_type == InputType.date:
            if not isinstance(config, (DateConstraints, EmptyConfig)):
                raise ValueError("date requires DateConstraints or Empty")
        elif input_type == InputType.time:
            if not isinstance(config, (TimeConstraints, EmptyConfig)):
                raise ValueError("time requires TimeConstraints or Empty")
            
        return self
