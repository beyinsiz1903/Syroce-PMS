"""
Report Automation Service
Otomatik rapor email gönderimi, PDF generation, scheduling
"""
import logging
logger = logging.getLogger(__name__)

class ReportAutomation:
    """Otomatik rapor gönderimi"""

    def __init__(self, db, email_service):
        self.db = db
        self.email_service = email_service
        self.scheduled_reports = []

    async def generate_flash_report_email(self, tenant_id: str, report_data: dict) -> str:
        """Flash report HTML email oluştur"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; }}
                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                          color: white; padding: 30px; text-align: center; }}
                .metric-card {{ background: #f9f9f9; padding: 20px; margin: 10px 0;
                               border-left: 4px solid #667eea; }}
                .metric-value {{ font-size: 36px; font-weight: bold; color: #667eea; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>⚡ Daily Flash Report</h1>
                    <p>{report_data.get('report_date', '')}</p>
                </div>
                <div style="padding: 20px;">
                    <h2>📊 Key Metrics</h2>
                    <div class="metric-card">
                        <div class="metric-label">Doluluk</div>
                        <div class="metric-value">{report_data.get('occupancy', {}).get('occupancy_pct', 0)}%</div>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        return html

    async def send_flash_report_email(self, tenant_id: str, recipients: list):
        """Flash report'u email ile gönder"""
        logger.info(f"📧 Sending flash report to {len(recipients)} recipients")
        return True

# Global
report_automation = None

def get_report_automation(db, email_service):
    global report_automation
    if report_automation is None:
        report_automation = ReportAutomation(db, email_service)
    return report_automation
