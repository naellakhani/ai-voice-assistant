# Email notification service for sending call summaries and transcripts to realtors after voice conversations.

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import os
import smtplib

def send_after_hours_notification(name, phone, email, reason_for_call, company, transcript):
    
    load_dotenv()  # Load email configuration from .env
    
    smtp_server = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    sender_email = os.getenv('SMTP_USERNAME')
    sender_password = os.getenv('SMTP_PASSWORD')
    recipient_email = os.getenv('SMTP_TO_EMAIL')
    
    # Print configuration (remove in production)
    print("Email Configuration:")
    print(f"SMTP Server: {smtp_server}")
    print(f"SMTP Port: {smtp_port}")
    print(f"From Email: {sender_email}")
    print(f"To Email: {recipient_email}") # Realtor's email
    
    if not all([smtp_server, smtp_port, sender_email, sender_password, recipient_email]):
        raise ValueError("Missing required email configuration")
    
    # Create message container
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'After Hours Call Report - {name}'
    msg['From'] = sender_email
    msg['To'] = recipient_email

    # Create HTML version of the email
    html = f"""
    <html>
        <body style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #333;">After Hours Call Report</h2>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 15px 0;">
                <h3 style="color: #444; margin-top: 0;">Lead Information</h3>
                <p style="margin: 5px 0;"><strong>Name:</strong> {name}</p>
                <p style="margin: 5px 0;"><strong>Phone:</strong> {phone}</p>
                <p style="margin: 5px 0;"><strong>Email:</strong> {email}</p>
                <p style="margin: 5px 0;"><strong>Reason for Call:</strong> {reason_for_call}</p>
                <p style="margin: 5px 0;"><strong>Company:</strong> {company}</p>
            </div>
            
            <div style="margin: 20px 0;">
                <h3 style="color: #444;">Call Transcript</h3>
                <div style="background-color: #fff; padding: 15px; border: 1px solid #ddd; border-radius: 5px;">
                    <pre style="white-space: pre-wrap; font-family: Arial, sans-serif; margin: 0;">{transcript}</pre>
                </div>
            </div>
            
            <p style="color: #888; font-size: 12px; margin-top: 30px;">
                This is an automated message. For immediate assistance, please contact your system administrator.
            </p>
        </body>
    </html>
    """
    
    # Create plain text version for email clients that don't support HTML
    text = f"""
    After Hours Call Report
    
    Lead Information:
    Name: {name}
    Phone: {phone}
    Email: {email}
    Reason for Call: {reason_for_call}
    Company: {company}
    
    Call Transcript:
    {transcript}
    
    This is an automated message. For immediate assistance, please contact your system administrator.
    """
    
    # Attach both plain text and HTML versions
    msg.attach(MIMEText(text, 'plain'))
    msg.attach(MIMEText(html, 'html'))
    
    try:
        print("Attempting to connect to SMTP server...")
        # Create secure SSL/TLS connection
        server = smtplib.SMTP(smtp_server, smtp_port)
        print("Connected to SMTP server")
        
        print("Starting TLS...")
        server.starttls()
        print("TLS started")
        
        print("Attempting login...")
        server.login(sender_email, sender_password)
        print("Login successful")
        
        # Send email
        print("Sending email...")
        server.send_message(msg)
        print(f"Email sent successfully to {recipient_email}")
        
    except Exception as e:
        print(f"Error sending after-hours notification: {e}")
        
    finally:
        try:
            print("Closing SMTP connection...")
            server.quit()
            print("SMTP connection closed")
        except Exception as e:
            print(f"Error closing SMTP connection: {str(e)}")