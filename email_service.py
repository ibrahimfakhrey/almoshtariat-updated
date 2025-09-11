import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import current_app

class EmailService:
    def __init__(self):
        # Gmail SMTP configuration
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.email = "suportalmohtariat@gmail.com"
        self.password = "kqgc gvqb gnqc sqip"
        self.mock_mode = False  # Set to True for development/testing without real SMTP
    
    def generate_verification_code(self):
        """Generate a 6-digit verification code"""
        return ''.join(random.choices(string.digits, k=6))
    
    def send_verification_email(self, to_email, verification_code, username):
        """Send verification email to user"""
        try:
            # Mock mode for development - simulates successful email sending
            if self.mock_mode:
                print(f"[MOCK EMAIL] Verification code for {to_email}: {verification_code}")
                print(f"[MOCK EMAIL] Username: {username}")
                print(f"[MOCK EMAIL] Email would be sent successfully in production")
                return True
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = "تأكيد البريد الإلكتروني - Email Verification"
            msg['From'] = self.email
            msg['To'] = to_email
            
            # Create HTML content
            html_content = f"""
            <!DOCTYPE html>
            <html dir="rtl" lang="ar">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>تأكيد البريد الإلكتروني</title>
                <style>
                    body {{
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        margin: 0;
                        padding: 20px;
                        direction: rtl;
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                        background: white;
                        border-radius: 15px;
                        box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                        overflow: hidden;
                    }}
                    .header {{
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        padding: 30px;
                        text-align: center;
                    }}
                    .header h1 {{
                        margin: 0;
                        font-size: 28px;
                        font-weight: 300;
                    }}
                    .content {{
                        padding: 40px 30px;
                        text-align: center;
                    }}
                    .verification-code {{
                        background: #f8f9fa;
                        border: 2px dashed #667eea;
                        border-radius: 10px;
                        padding: 20px;
                        margin: 30px 0;
                        font-size: 32px;
                        font-weight: bold;
                        color: #667eea;
                        letter-spacing: 5px;
                    }}
                    .message {{
                        font-size: 16px;
                        line-height: 1.6;
                        color: #333;
                        margin-bottom: 20px;
                    }}
                    .footer {{
                        background: #f8f9fa;
                        padding: 20px;
                        text-align: center;
                        color: #666;
                        font-size: 14px;
                    }}
                    .logo {{
                        width: 60px;
                        height: 60px;
                        background: white;
                        border-radius: 50%;
                        margin: 0 auto 20px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 24px;
                        color: #667eea;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <div class="logo">📧</div>
                        <h1>تأكيد البريد الإلكتروني</h1>
                        <p>Email Verification</p>
                    </div>
                    <div class="content">
                        <p class="message">
                            مرحباً <strong>{username}</strong>،<br>
                            Hello <strong>{username}</strong>,
                        </p>
                        <p class="message">
                            شكراً لتسجيلك في منصتنا. يرجى استخدام الرمز التالي لتأكيد بريدك الإلكتروني:<br>
                            Thank you for registering on our platform. Please use the following code to verify your email:
                        </p>
                        <div class="verification-code">
                            {verification_code}
                        </div>
                        <p class="message">
                            هذا الرمز صالح لمدة 15 دقيقة فقط.<br>
                            This code is valid for 15 minutes only.
                        </p>
                    </div>
                    <div class="footer">
                        <p>إذا لم تقم بإنشاء هذا الحساب، يرجى تجاهل هذا البريد الإلكتروني.</p>
                        <p>If you didn't create this account, please ignore this email.</p>
                        <p><strong>المشتريات - Almoshtriyat</strong></p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Create plain text version
            text_content = f"""
            مرحباً {username},
            Hello {username},
            
            شكراً لتسجيلك في منصتنا. رمز التأكيد الخاص بك هو: {verification_code}
            Thank you for registering. Your verification code is: {verification_code}
            
            هذا الرمز صالح لمدة 15 دقيقة فقط.
            This code is valid for 15 minutes only.
            
            المشتريات - Almoshtriyat
            """
            
            # Attach parts
            part1 = MIMEText(text_content, 'plain', 'utf-8')
            part2 = MIMEText(html_content, 'html', 'utf-8')
            
            msg.attach(part1)
            msg.attach(part2)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email, self.password)
                server.send_message(msg)
            
            return True
            
        except Exception as e:
            error_msg = str(e)
            print(f"Error sending email: {error_msg}")
            
            # Provide helpful error messages
            if "Authentication unsuccessful" in error_msg:
                print("SMTP Authentication failed. Possible solutions:")
                print("1. Enable 2-factor authentication and use an app-specific password")
                print("2. Check if 'Less secure app access' is enabled (not recommended)")
                print("3. Verify the email and password are correct")
            elif "Connection refused" in error_msg:
                print("SMTP server connection refused. Check server and port settings.")
            
            return False
    
    def is_code_expired(self, sent_at, minutes=15):
        """Check if verification code has expired"""
        if not sent_at:
            return True
        expiry_time = sent_at + timedelta(minutes=minutes)
        return datetime.utcnow() > expiry_time

# Create global instance
email_service = EmailService()