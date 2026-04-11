"""Compatibility alias — use hr_client instead."""
from .hr_client import AUDIT_TRUNCATE_LEN as AUDIT_TRUNCATE_LEN  # noqa: F401
from .hr_client import DEFAULT_PER_PAGE as DEFAULT_PER_PAGE  # noqa: F401
from .hr_client import HOTELRUNNER_API_BASE as HOTELRUNNER_API_BASE  # noqa: F401
from .hr_client import HOTELRUNNER_MOCK_BASE as HOTELRUNNER_MOCK_BASE  # noqa: F401
from .hr_client import HOTELRUNNER_SANDBOX_BASE as HOTELRUNNER_SANDBOX_BASE  # noqa: F401
from .hr_client import HotelRunnerClient as HotelRunnerClient  # noqa: F401
from .hr_client import MASK_KEYS as MASK_KEYS  # noqa: F401
from .hr_client import MAX_PAGINATION_PAGES as MAX_PAGINATION_PAGES  # noqa: F401
from .hr_client import VALID_ENVIRONMENTS as VALID_ENVIRONMENTS  # noqa: F401
from .hr_client import _mask_params as _mask_params  # noqa: F401
from .hr_client import _truncate as _truncate  # noqa: F401

__all__ = [
    "AUDIT_TRUNCATE_LEN",
    "DEFAULT_PER_PAGE",
    "HOTELRUNNER_API_BASE",
    "HOTELRUNNER_MOCK_BASE",
    "HOTELRUNNER_SANDBOX_BASE",
    "HotelRunnerClient",
    "MASK_KEYS",
    "MAX_PAGINATION_PAGES",
    "VALID_ENVIRONMENTS",
    "_mask_params",
    "_truncate",
]
