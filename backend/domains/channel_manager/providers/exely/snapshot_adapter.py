import logging
from datetime import datetime, timedelta

from domains.channel_manager.ari.provider_snapshot_contract import (
    CredentialsMissing,
    ProviderSnapshotAdapter,
    ProviderSnapshotUnavailable,
)
from domains.channel_manager.providers.exely import soap_builder
from domains.channel_manager.providers.exely.client import ExelySoapTransport
from domains.channel_manager.providers.exely.response_parser import _attr, _ns, _text, parse_soap_response

logger = logging.getLogger("exely.snapshot_adapter")


class ExelySnapshotAdapter(ProviderSnapshotAdapter):
    async def fetch_snapshot(
        self,
        tenant_id: str,
        property_id: str,
        credentials: dict,
        *,
        date_from: str,
        date_to: str,
    ) -> list[dict]:
        username = credentials.get("username")
        password = credentials.get("password")
        hotel_code = credentials.get("hotel_code")

        if not username or not password or not hotel_code:
            raise CredentialsMissing("Exely credentials 'username', 'password', and 'hotel_code' are required.")

        endpoint_url = credentials.get("api_url") or "https://pmsconnect.test.hopenapi.com/api/PMSConnect.svc"

        try:
            transport = ExelySoapTransport(endpoint_url=endpoint_url)
            xml = soap_builder.build_hotel_avail_rq(username, password, hotel_code, date_from, date_to)
            soap_action = soap_builder.get_soap_action_uri("OTA_HotelAvailRQ")
            raw_bytes = await transport.send_soap(xml, soap_action)
        except Exception as e:
            raise ProviderSnapshotUnavailable(f"Exely SOAP API connection failed: {e}") from e

        envelope = parse_soap_response(raw_bytes)
        if not envelope["success"]:
            raise ProviderSnapshotUnavailable(f"Exely SOAP request failed: {envelope.get('error')}")

        body = envelope["body"]
        if body is None:
            raise ProviderSnapshotUnavailable("Exely SOAP response body is empty.")

        # Check for OTA Errors
        errors_el = body.find(_ns("Errors"))
        if errors_el is not None:
            error_msgs = []
            for err in errors_el.findall(_ns("Error")):
                code = _attr(err, "Code", "")
                msg = _text(err, "Unknown error")
                error_msgs.append(f"OTA Error [{code}]: {msg}")
            if error_msgs:
                raise ProviderSnapshotUnavailable("; ".join(error_msgs))

        avail_map = {}
        normalized = []

        # 1. Parse all Availabilities first to build map
        for room_stay in body.iter(_ns("RoomStay")):
            avail_el = room_stay.find(_ns("Availability"))
            if avail_el is not None:
                for qty_el in avail_el.findall(_ns("Qty")):
                    rc = _attr(qty_el, "RoomTypeCode")
                    dt = _attr(qty_el, "Date")
                    val = _text(qty_el)
                    if rc and dt and val:
                        try:
                            avail_map[(rc, dt)] = int(val)
                        except ValueError:
                            pass

        # 2. Parse room rates
        for room_stay in body.iter(_ns("RoomStay")):
            room_rates_el = room_stay.find(_ns("RoomRates"))
            if room_rates_el is not None:
                for room_rate in room_rates_el.findall(_ns("RoomRate")):
                    rc = _attr(room_rate, "RoomTypeCode")
                    rate_code = _attr(room_rate, "RatePlanCode")
                    if not rc or not rate_code:
                        continue

                    rates_el = room_rate.find(_ns("Rates"))
                    if rates_el is not None:
                        for rate in rates_el.findall(_ns("Rate")):
                            start_str = _attr(rate, "Start")
                            end_str = _attr(rate, "End")
                            if not start_str or not end_str:
                                continue

                            try:
                                start_dt = datetime.strptime(start_str, "%Y-%m-%d")
                                end_dt = datetime.strptime(end_str, "%Y-%m-%d")
                            except ValueError:
                                continue

                            # Parse BaseByGuestAmts -> BaseByGuestAmt -> AmountBeforeTax
                            rate_val = None
                            base_amts = rate.find(_ns("BaseByGuestAmts"))
                            if base_amts is not None:
                                base_amt = base_amts.find(_ns("BaseByGuestAmt"))
                                if base_amt is not None:
                                    try:
                                        rate_val = float(_attr(base_amt, "AmountBeforeTax"))
                                    except ValueError:
                                        pass

                            # Parse AdditionalGuestAmounts -> AdditionalGuestAmount
                            min_stay = None
                            stop_sell = None
                            add_amts = rate.find(_ns("AdditionalGuestAmounts"))
                            if add_amts is not None:
                                add_amt = add_amts.find(_ns("AdditionalGuestAmount"))
                                if add_amt is not None:
                                    min_stay_str = _attr(add_amt, "MinStay")
                                    if min_stay_str:
                                        try:
                                            min_stay = int(min_stay_str)
                                        except ValueError:
                                            pass
                                    stop_sell_str = _attr(add_amt, "StopSell")
                                    if stop_sell_str:
                                        stop_sell = stop_sell_str.lower() == "true"

                            # Iterate date range [start, end)
                            curr_dt = start_dt
                            while curr_dt < end_dt:
                                curr_str = curr_dt.strftime("%Y-%m-%d")
                                qty = avail_map.get((rc, curr_str))

                                normalized.append(
                                    {
                                        "room_type_code": str(rc),
                                        "rate_plan_code": str(rate_code),
                                        "date": curr_str,
                                        "availability": qty,
                                        "rate": rate_val,
                                        "restrictions": {"min_stay_through": min_stay, "stop_sell": stop_sell},
                                    }
                                )
                                curr_dt += timedelta(days=1)

        return normalized
