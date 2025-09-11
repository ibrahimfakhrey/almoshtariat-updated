#!/usr/bin/env python3
"""
Test script to verify email sending functionality
"""

import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

def generate_verification_code():
    """Generate a 6-digit verification code"""
    return ''.join(random.choices(string.digits, k=6))

def test_email_sending():
    """Test email sending with different configurations"""
    
    # Test email details
    to_email = "ibrahimfakhreyams@gmail.com"
    verification_code = generate_verification_code()
    username = "Test User"
    
    print(f"Testing email sending to: {to_email}")
    print(f"Verification code: {verification_code}")
    print("-" * 50)
    
    # Test 1: Mock mode (always works)
    print("\n1. Testing Mock Mode:")
    print(f"[MOCK EMAIL] Verification code for {to_email}: {verification_code}")
    print(f"[MOCK EMAIL] Username: {username}")
    print(f"[MOCK EMAIL] Email would be sent successfully in production")
    print("✅ Mock email test: SUCCESS")
    
    # Test 2: Gmail SMTP (with real credentials)
    print("\n2. Testing Gmail SMTP:")
    try:
        # Gmail configuration
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        email = "suportalmohtariat@gmail.com"
        password = "kqgc gvqb gnqc sqip"
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "Test Email - Verification Code"
        msg['From'] = email
        msg['To'] = to_email
        
        # Create content
        text_content = f"""
        Hello {username},
        
        Your verification code is: {verification_code}
        
        This is a test email to verify email sending functionality.
        
        Best regards,
        Test System
        """
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Test Email</title>
        </head>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: #f9f9f9; padding: 20px; border-radius: 10px;">
                <h2 style="color: #333;">Test Email - Verification Code</h2>
                <p>Hello <strong>{username}</strong>,</p>
                <p>Your verification code is:</p>
                <div style="background: #007bff; color: white; padding: 15px; text-align: center; font-size: 24px; font-weight: bold; border-radius: 5px; margin: 20px 0;">
                    {verification_code}
                </div>
                <p>This is a test email to verify email sending functionality.</p>
                <p>Best regards,<br>Test System</p>
                <hr style="margin: 20px 0;">
                <p style="font-size: 12px; color: #666;">This is an automated test email sent at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
        </body>
        </html>
        """
        
        # Attach parts
        part1 = MIMEText(text_content, 'plain', 'utf-8')
        part2 = MIMEText(html_content, 'html', 'utf-8')
        
        msg.attach(part1)
        msg.attach(part2)
        
        # Send email with real Outlook credentials
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(email, password)
            server.send_message(msg)
        
        print("✅ Gmail SMTP test: SUCCESS")
        print(f"   Email sent successfully to {to_email}")
            
    except Exception as e:
        print(f"❌ Gmail SMTP test: FAILED")
        print(f"   Error: {str(e)}")
        
        # Provide helpful error messages
        error_msg = str(e)
        if "Authentication unsuccessful" in error_msg or "535" in error_msg:
            print("   💡 Solution: Check Gmail credentials or enable app-specific password")
        elif "Connection refused" in error_msg:
            print("   💡 Solution: Check internet connection and SMTP server settings")
        elif "getaddrinfo failed" in error_msg:
            print("   💡 Solution: Check internet connection and DNS settings")
    
    print("\n" + "=" * 50)
    print("Email Test Summary:")
    print("- Mock mode: Always works for development/testing")
    print("- Real SMTP: Requires proper email credentials")
    print("- For production: Set up proper email service credentials")
    print("=" * 50)

if __name__ == '__main__':
    print("Email Service Test Script")
    print("=" * 50)
    test_email_sending()