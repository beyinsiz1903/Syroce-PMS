"""
HotelRunner Provider — Pagination Handler
===========================================

Centralizes pagination logic for the reservations endpoint.
Includes safety limits, duplicate page detection, and infinite loop protection.
"""
import logging
from typing import Any, Awaitable, Callable, Dict, List

from .errors import HotelRunnerPaginationError

logger = logging.getLogger("hotelrunner.paginator")

DEFAULT_MAX_PAGES = 50
DEFAULT_PER_PAGE = 50


class HotelRunnerPaginator:
    """
    Handles multi-page fetches from HotelRunner API.
    Provides safety guards against infinite loops and duplicate pages.
    """

    def __init__(self, max_pages: int = DEFAULT_MAX_PAGES):
        self.max_pages = max_pages

    async def fetch_all_pages(
        self,
        fetch_page_fn: Callable[[int], Awaitable[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """
        Fetch all pages by calling fetch_page_fn(page_number).

        fetch_page_fn should return:
            {"reservations": [...], "pages": total_pages, ...}

        Returns aggregated list of all reservation dicts.
        """
        all_items: List[Dict[str, Any]] = []
        seen_first_ids: set[str] = set()
        page = 1

        while page <= self.max_pages:
            logger.debug("Fetching page %d/%d", page, self.max_pages)

            data = await fetch_page_fn(page)
            items = data.get("reservations", [])
            total_pages = data.get("pages", 1)

            if not items:
                logger.info("Empty page %d, stopping pagination", page)
                break

            # Duplicate page detection
            first_id = str(
                items[0].get("hr_number")
                or items[0].get("reservation_id")
                or items[0].get("message_uid", "")
            )
            if first_id and first_id in seen_first_ids:
                logger.warning(
                    "Duplicate page detected at page %d (first_id=%s), stopping",
                    page, first_id,
                )
                break
            if first_id:
                seen_first_ids.add(first_id)

            all_items.extend(items)

            if page >= total_pages:
                break
            page += 1

        if page > self.max_pages:
            logger.warning(
                "Pagination safety limit reached: %d pages, %d items",
                self.max_pages, len(all_items),
            )
            raise HotelRunnerPaginationError(
                max_pages=self.max_pages,
                fetched_count=len(all_items),
            )

        logger.info(
            "Pagination complete: %d pages fetched, %d total items",
            page, len(all_items),
        )
        return all_items
