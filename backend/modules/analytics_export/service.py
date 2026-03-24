"""
Analytics Export Service.
CSV/Excel/PDF-ready exports for revenue, operations, guests, messaging, autopilot, audit.
"""
import csv
import io
import logging
import uuid
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


class ExportFormat:
    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"


class ExportStatus:
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


REPORT_TYPES = [
    "revenue_ml_outputs",
    "operational_ai_forecasts",
    "guest_intelligence_summary",
    "messaging_delivery_performance",
    "autopilot_decisions",
    "audit_summary",
    "property_comparison",
    "management_summary",
]


def new_export_job(
    tenant_id: str,
    report_type: str,
    export_format: str,
    filters: dict,
    requested_by: str,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "report_type": report_type,
        "export_format": export_format,
        "filters": filters,
        "requested_by": requested_by,
        "status": ExportStatus.PENDING,
        "file_path": None,
        "file_size_bytes": None,
        "row_count": None,
        "error_message": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    }


class AnalyticsExportService:
    """Generates exportable analytics reports."""

    def __init__(self, db):
        self.db = db

    async def create_export(self, tenant_id: str, report_type: str,
                            export_format: str, filters: dict, user_id: str) -> dict:
        if report_type not in REPORT_TYPES:
            return {"success": False, "error": f"Unknown report type: {report_type}"}

        job = new_export_job(tenant_id, report_type, export_format, filters, user_id)
        await self.db.analytics_export_jobs.insert_one(job)

        # generate synchronously for now (< 30s for most reports)
        result = await self._generate(job)
        return result

    async def _generate(self, job: dict) -> dict:
        job_id = job["id"]
        tenant_id = job["tenant_id"]
        report_type = job["report_type"]
        export_format = job["export_format"]
        filters = job.get("filters", {})

        await self.db.analytics_export_jobs.update_one(
            {"id": job_id}, {"$set": {"status": ExportStatus.GENERATING}}
        )

        try:
            data = await self._fetch_data(tenant_id, report_type, filters)
            rows = data.get("rows", [])
            headers = data.get("headers", [])

            if export_format == ExportFormat.CSV:
                content = self._to_csv(headers, rows)
            elif export_format == ExportFormat.JSON:
                import json
                content = json.dumps({"headers": headers, "rows": rows}, ensure_ascii=False, indent=2)
            else:
                content = self._to_csv(headers, rows)  # excel uses csv for now

            await self.db.analytics_export_jobs.update_one(
                {"id": job_id},
                {"$set": {
                    "status": ExportStatus.COMPLETED,
                    "row_count": len(rows),
                    "file_size_bytes": len(content.encode("utf-8")) if isinstance(content, str) else len(content),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }},
            )

            return {
                "success": True,
                "job_id": job_id,
                "report_type": report_type,
                "format": export_format,
                "row_count": len(rows),
                "headers": headers,
                "rows": rows,
                "content": content,
            }
        except Exception as e:
            logger.exception("Export generation failed")
            await self.db.analytics_export_jobs.update_one(
                {"id": job_id},
                {"$set": {"status": ExportStatus.FAILED, "error_message": str(e)[:300]}},
            )
            return {"success": False, "error": str(e)[:300], "job_id": job_id}

    async def _fetch_data(self, tenant_id: str, report_type: str, filters: dict) -> dict:
        """Fetch data for the given report type."""
        date_from = filters.get("date_from", (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d"))
        date_to = filters.get("date_to", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        filters.get("property_id")

        if report_type == "revenue_ml_outputs":
            return await self._revenue_ml_data(tenant_id, date_from, date_to)
        elif report_type == "operational_ai_forecasts":
            return await self._operational_ai_data(tenant_id, date_from, date_to)
        elif report_type == "guest_intelligence_summary":
            return await self._guest_data(tenant_id)
        elif report_type == "messaging_delivery_performance":
            return await self._messaging_data(tenant_id, date_from, date_to)
        elif report_type == "autopilot_decisions":
            return await self._autopilot_data(tenant_id, date_from, date_to)
        elif report_type == "audit_summary":
            return await self._audit_data(tenant_id, date_from, date_to)
        elif report_type == "management_summary":
            return await self._management_summary(tenant_id, date_from, date_to)
        else:
            return {"headers": [], "rows": []}

    async def _revenue_ml_data(self, tenant_id, date_from, date_to) -> dict:
        snapshots = await self.db.ml_snapshots.find(
            {"tenant_id": tenant_id, "model_type": "revenue_ml", "created_at": {"$gte": date_from}},
            {"_id": 0}
        ).sort("created_at", -1).to_list(100)
        headers = ["Date", "Model Type", "Confidence", "Snapshot ID"]
        rows = [[s.get("created_at", ""), s.get("model_type", ""), s.get("confidence_avg", ""), s.get("id", "")] for s in snapshots]
        return {"headers": headers, "rows": rows}

    async def _operational_ai_data(self, tenant_id, date_from, date_to) -> dict:
        snapshots = await self.db.ml_snapshots.find(
            {"tenant_id": tenant_id, "model_type": "operational_ai", "created_at": {"$gte": date_from}},
            {"_id": 0}
        ).sort("created_at", -1).to_list(100)
        headers = ["Date", "Model Type", "Confidence", "Snapshot ID"]
        rows = [[s.get("created_at", ""), s.get("model_type", ""), s.get("confidence_avg", ""), s.get("id", "")] for s in snapshots]
        return {"headers": headers, "rows": rows}

    async def _guest_data(self, tenant_id) -> dict:
        guests = await self.db.guests.find(
            {"tenant_id": tenant_id}, {"_id": 0, "id": 1, "name": 1, "email": 1, "total_stays": 1, "total_revenue": 1}
        ).to_list(500)
        headers = ["Guest ID", "Name", "Email", "Total Stays", "Total Revenue"]
        rows = [[g.get("id", ""), g.get("name", ""), g.get("email", ""), g.get("total_stays", 0), g.get("total_revenue", 0)] for g in guests]
        return {"headers": headers, "rows": rows}

    async def _messaging_data(self, tenant_id, date_from, date_to) -> dict:
        logs = await self.db.messaging_delivery_logs.find(
            {"tenant_id": tenant_id, "created_at": {"$gte": date_from}},
            {"_id": 0}
        ).sort("created_at", -1).to_list(500)
        headers = ["Date", "Channel", "Recipient", "Status", "Use Case", "Error"]
        rows = [[l.get("created_at", ""), l.get("channel", ""), l.get("recipient", ""),
                 l.get("status", ""), l.get("use_case", ""), l.get("error_message", "")] for l in logs]
        return {"headers": headers, "rows": rows}

    async def _autopilot_data(self, tenant_id, date_from, date_to) -> dict:
        items = await self.db.revenue_approval_queue.find(
            {"tenant_id": tenant_id, "created_at": {"$gte": date_from}},
            {"_id": 0}
        ).sort("created_at", -1).to_list(500)
        headers = ["Date", "Room Type", "Target Date", "Current Price", "Recommended", "Confidence", "Status"]
        rows = [[i.get("created_at", ""), i.get("room_type", ""), i.get("target_date", ""),
                 i.get("current_price", ""), i.get("recommended_price", ""),
                 i.get("confidence", ""), i.get("status", "")] for i in items]
        return {"headers": headers, "rows": rows}

    async def _audit_data(self, tenant_id, date_from, date_to) -> dict:
        audits = await self.db.audit_logs.find(
            {"tenant_id": tenant_id, "timestamp": {"$gte": date_from}},
            {"_id": 0}
        ).sort("timestamp", -1).to_list(500)
        headers = ["Timestamp", "User", "Action", "Entity Type", "Entity ID"]
        rows = [[a.get("timestamp", ""), a.get("user_id", ""), a.get("action", ""),
                 a.get("entity_type", ""), a.get("entity_id", "")] for a in audits]
        return {"headers": headers, "rows": rows}

    async def _management_summary(self, tenant_id, date_from, date_to) -> dict:
        # aggregate multiple sources into a summary
        headers = ["Metric", "Value", "Period"]
        rows = []
        # messaging stats
        msg_count = await self.db.messaging_delivery_logs.count_documents(
            {"tenant_id": tenant_id, "created_at": {"$gte": date_from}})
        rows.append(["Total Messages Sent", msg_count, f"{date_from} - {date_to}"])
        # autopilot stats
        ap_count = await self.db.revenue_approval_queue.count_documents(
            {"tenant_id": tenant_id, "created_at": {"$gte": date_from}})
        rows.append(["Autopilot Decisions", ap_count, f"{date_from} - {date_to}"])
        # ML runs
        ml_count = await self.db.ml_execution_jobs.count_documents(
            {"tenant_id": tenant_id, "created_at": {"$gte": date_from}})
        rows.append(["ML Model Runs", ml_count, f"{date_from} - {date_to}"])
        return {"headers": headers, "rows": rows}

    def _to_csv(self, headers: list, rows: list) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        return output.getvalue()

    async def get_export_history(self, tenant_id: str, limit: int = 20) -> list:
        return await self.db.analytics_export_jobs.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).sort("created_at", -1).to_list(limit)

    async def get_available_reports(self) -> list:
        return [
            {"type": rt, "label": rt.replace("_", " ").title()}
            for rt in REPORT_TYPES
        ]
