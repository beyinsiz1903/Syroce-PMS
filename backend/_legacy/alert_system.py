"""
Alert System - Otomatik hata bildirimi
Sistem hatası olduğunda otomatik email/SMS gönderir
"""
from datetime import datetime, timezone
import os
from typing import Dict, Any

class AlertManager:
    """Otomatik alert sistemi"""
    
    def __init__(self):
        self.admin_email = os.getenv('ADMIN_EMAIL', 'admin@yourdomain.com')
        self.alert_threshold = {
            'error_rate': 5,  # 5 error in 5 mins
            'response_time': 1000,  # 1000ms
            'cpu_usage': 90,  # 90%
            'memory_usage': 90  # 90%
        }
        self.recent_errors = []
    
    async def check_system_health(self, db):
        """Sistem sağlığını kontrol et ve gerekirse alert gönder"""
        try:
            # Check error rate
            error_count = await db.error_logs.count_documents({
                'timestamp': {'$gte': datetime.now(timezone.utc).isoformat()}
            })
            
            if error_count > self.alert_threshold['error_rate']:
                await self.send_alert(
                    severity='high',
                    title='Yüksek Hata Oranı',
                    message=f'{error_count} hata son 5 dakikada',
                    details={'error_count': error_count}
                )
            
            # Check response times
            # Check CPU/Memory
            # etc.
            
        except Exception as e:
            print(f"Alert system error: {e}")
    
    async def send_alert(self, severity: str, title: str, message: str, details: Dict[str, Any]):
        """
        Alert gönder - Email, SMS, Slack vb.
        
        Args:
            severity: 'low', 'medium', 'high', 'critical'
            title: Alert başlığı
            message: Kısa mesaj
            details: Detaylı bilgi
        """
        alert_data = {
            'severity': severity,
            'title': title,
            'message': message,
            'details': details,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # Burada email/SMS/Slack entegrasyonu yapılacak
        print(f"🚨 ALERT: {severity.upper()} - {title}")
        print(f"   Message: {message}")
        print(f"   Details: {details}")
        
        # TODO: Gerçek alerting servisi entegrasyonu
        # - Email (SendGrid, AWS SES)
        # - SMS (Twilio)
        # - Slack webhook
        # - WhatsApp Business API
        
        return alert_data
    
    async def log_error(self, error_type: str, error_message: str, context: Dict):
        """Hataları logla ve kritikse alert gönder"""
        error_log = {
            'type': error_type,
            'message': error_message,
            'context': context,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # Kritik hatalarda anında alert
        critical_errors = ['database_connection', 'payment_failed', 'data_loss']
        if error_type in critical_errors:
            await self.send_alert(
                severity='critical',
                title=f'Kritik Hata: {error_type}',
                message=error_message,
                details=context
            )
        
        return error_log

# Global instance
alert_manager = AlertManager()
