"""
Email Service - AWS SES SMTP Implementation
Gerçek e-posta gönderimi için AWS SES kullanır
"""
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

class EmailService:
    """Email service with AWS SES SMTP support"""
    
    def __init__(self):
        # Email mode: "production" veya "mock"
        self.mode = os.environ.get('EMAIL_MODE', 'production')
        
        # AWS SES SMTP Settings
        self.smtp_host = os.environ.get('SMTP_HOST', 'email-smtp.eu-central-1.amazonaws.com')
        self.smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        self.smtp_username = os.environ.get('SMTP_USERNAME', '')
        self.smtp_password = os.environ.get('SMTP_PASSWORD', '')
        self.sender_email = os.environ.get('SENDER_EMAIL', 'info@syroce.com')
        self.sender_name = os.environ.get('SENDER_NAME', 'Syroce')
        
        print(f"📧 Email Service initialized in {self.mode} mode")
        if self.mode == "production" and self.smtp_username:
            print(f"✅ AWS SES configured: {self.smtp_host}:{self.smtp_port}")
    
    def generate_verification_code(self) -> str:
        """6 haneli onay kodu oluştur"""
        return str(random.randint(100000, 999999))
    
    def generate_reset_token(self) -> str:
        """Şifre sıfırlama token'ı oluştur"""
        import secrets
        return secrets.token_urlsafe(32)
    
    def _create_verification_email_html(self, code: str, name: str = None) -> str:
        """HTML formatted verification email"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                          color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .code-box {{ background: white; border: 2px dashed #667eea; padding: 20px; 
                           text-align: center; font-size: 32px; font-weight: bold; 
                           letter-spacing: 8px; margin: 20px 0; border-radius: 8px; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
                .warning {{ color: #e74c3c; font-size: 14px; margin-top: 15px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>✨ Syroce'ye Hoş Geldiniz!</h1>
                </div>
                <div class="content">
                    <p>Merhaba{' ' + name if name else ''},</p>
                    <p>Syroce hesabınızı oluşturmak için e-posta adresinizi doğrulamanız gerekiyor.</p>
                    <p><strong>Doğrulama kodunuz:</strong></p>
                    <div class="code-box">{code}</div>
                    <p>Bu kodu kayıt ekranına girerek hesabınızı aktive edebilirsiniz.</p>
                    <p class="warning">⏰ Bu kod 15 dakika geçerlidir.</p>
                    <p class="warning">🔒 Bu kodu kimseyle paylaşmayın.</p>
                </div>
                <div class="footer">
                    <p>© 2025 Syroce - Otel Yönetim Sistemi</p>
                    <p>Bu e-postayı siz talep etmediniz mi? Güvenle görmezden gelebilirsiniz.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _create_password_reset_email_html(self, code: str, name: str = None) -> str:
        """HTML formatted password reset email"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%); 
                          color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .code-box {{ background: white; border: 2px dashed #e74c3c; padding: 20px; 
                           text-align: center; font-size: 32px; font-weight: bold; 
                           letter-spacing: 8px; margin: 20px 0; border-radius: 8px; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
                .warning {{ color: #e74c3c; font-size: 14px; margin-top: 15px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔐 Şifre Sıfırlama</h1>
                </div>
                <div class="content">
                    <p>Merhaba{' ' + name if name else ''},</p>
                    <p>Syroce hesabınız için şifre sıfırlama talebinde bulundunuz.</p>
                    <p><strong>Şifre sıfırlama kodunuz:</strong></p>
                    <div class="code-box">{code}</div>
                    <p>Bu kodu kullanarak yeni bir şifre belirleyebilirsiniz.</p>
                    <p class="warning">⏰ Bu kod 15 dakika geçerlidir.</p>
                    <p class="warning">🔒 Bu kodu kimseyle paylaşmayın.</p>
                    <p><strong>Bu talebi siz yapmadınız mı?</strong><br>
                    Güvenle bu e-postayı görmezden gelebilirsiniz. Şifreniz değişmeyecektir.</p>
                </div>
                <div class="footer">
                    <p>© 2025 Syroce - Otel Yönetim Sistemi</p>
                    <p>Güvenlik nedenleriyle bu bağlantı kısa sürede sona erecektir.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _create_welcome_email_html(self, name: str) -> str:
        """HTML formatted welcome email"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #2ecc71 0%, #27ae60 100%); 
                          color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .button {{ background: #667eea; color: white; padding: 15px 30px; 
                          text-decoration: none; border-radius: 5px; display: inline-block; 
                          margin: 20px 0; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎉 Hoş Geldiniz!</h1>
                </div>
                <div class="content">
                    <p>Merhaba {name},</p>
                    <p>Syroce ailesine hoş geldiniz! Hesabınız başarıyla oluşturuldu.</p>
                    <p>Artık otel yönetim sisteminizi kullanmaya başlayabilirsiniz:</p>
                    <ul>
                        <li>✅ Rezervasyon Yönetimi</li>
                        <li>✅ Misafir Takibi</li>
                        <li>✅ Oda Durumları</li>
                        <li>✅ Gelir Raporları</li>
                        <li>✅ Ve daha fazlası...</li>
                    </ul>
                    <p style="text-align: center;">
                        <a href="https://syroce.com/login" class="button">Hemen Başla</a>
                    </p>
                    <p>Herhangi bir sorunuz olursa, destek ekibimiz size yardımcı olmaktan mutluluk duyar.</p>
                </div>
                <div class="footer">
                    <p>© 2025 Syroce - Otel Yönetim Sistemi</p>
                    <p>Destek: info@syroce.com</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _send_email_smtp(self, to_email: str, subject: str, html_content: str, text_content: str) -> bool:
        """Send email via AWS SES SMTP"""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.sender_name} <{self.sender_email}>"
            msg['To'] = to_email
            
            # Add both plain text and HTML versions
            part1 = MIMEText(text_content, 'plain', 'utf-8')
            part2 = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(part1)
            msg.attach(part2)
            
            # Connect to SMTP server
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.set_debuglevel(0)  # Set to 1 for debugging
            server.starttls()  # Enable TLS
            server.login(self.smtp_username, self.smtp_password)
            
            # Send email
            server.sendmail(self.sender_email, to_email, msg.as_string())
            server.quit()
            
            print(f"✅ Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to send email via SMTP: {e}")
            return False
    
    async def send_verification_code(self, email: str, code: str, name: str = None) -> bool:
        """E-posta doğrulama kodu gönder"""
        subject = "Syroce - E-posta Doğrulama Kodu"
        html_content = self._create_verification_email_html(code, name)
        text_content = f"""
Merhaba{' ' + name if name else ''},

Syroce hesabınızı oluşturmak için e-posta adresinizi doğrulamanız gerekiyor.

Doğrulama kodunuz: {code}

Bu kod 15 dakika geçerlidir.
Bu kodu kimseyle paylaşmayın.

© 2025 Syroce - Otel Yönetim Sistemi
        """
        
        if self.mode == "production" and self.smtp_username and self.smtp_password:
            # Send real email via AWS SES
            return self._send_email_smtp(email, subject, html_content, text_content)
        else:
            # Mock mode - print to console
            print("\n" + "="*60)
            print("📧 E-POSTA DOĞRULAMA KODU")
            print("="*60)
            print(f"Alıcı: {email}")
            if name:
                print(f"İsim: {name}")
            print(f"Kod: {code}")
            print("Geçerlilik: 15 dakika")
            print(f"Gönderim Zamanı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("="*60 + "\n")
            return True
    
    async def send_password_reset_code(self, email: str, code: str, name: str = None) -> bool:
        """Şifre sıfırlama kodu gönder"""
        subject = "Syroce - Şifre Sıfırlama Kodu"
        html_content = self._create_password_reset_email_html(code, name)
        text_content = f"""
Merhaba{' ' + name if name else ''},

Syroce hesabınız için şifre sıfırlama talebinde bulundunuz.

Şifre sıfırlama kodunuz: {code}

Bu kod 15 dakika geçerlidir.
Bu kodu kimseyle paylaşmayın.

Bu talebi siz yapmadınız mı? Güvenle bu e-postayı görmezden gelebilirsiniz.

© 2025 Syroce - Otel Yönetim Sistemi
        """
        
        if self.mode == "production" and self.smtp_username and self.smtp_password:
            # Send real email via AWS SES
            return self._send_email_smtp(email, subject, html_content, text_content)
        else:
            # Mock mode - print to console
            print("\n" + "="*60)
            print("🔐 ŞİFRE SIFIRLAMA KODU")
            print("="*60)
            print(f"Alıcı: {email}")
            if name:
                print(f"İsim: {name}")
            print(f"Kod: {code}")
            print("Geçerlilik: 15 dakika")
            print(f"Gönderim Zamanı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("="*60 + "\n")
            return True
    
    async def send_welcome_email(self, email: str, name: str) -> bool:
        """Hoşgeldin e-postası gönder"""
        subject = "Syroce'ye Hoş Geldiniz! 🎉"
        html_content = self._create_welcome_email_html(name)
        text_content = f"""
Merhaba {name},

Syroce ailesine hoş geldiniz! Hesabınız başarıyla oluşturuldu.

Artık otel yönetim sisteminizi kullanmaya başlayabilirsiniz.

© 2025 Syroce - Otel Yönetim Sistemi
Destek: info@syroce.com
        """
        
        if self.mode == "production" and self.smtp_username and self.smtp_password:
            # Send real email via AWS SES
            return self._send_email_smtp(email, subject, html_content, text_content)
        else:
            # Mock mode - print to console
            print("\n" + "="*60)
            print("🎉 HOŞGELDİN E-POSTASI")
            print("="*60)
            print(f"Alıcı: {email}")
            print(f"İsim: {name}")
            print("Mesaj: Hesabınız başarıyla oluşturuldu!")
            print(f"Gönderim Zamanı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("="*60 + "\n")
            return True

# Global email service instance
email_service = EmailService()
