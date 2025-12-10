import smtplib
from email.mime.text import MIMEText

# Sender & receiver
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "durgaasus@gmail.com"
SENDER_PASSWORD = "rlbo tdsd zmqr mllc"  # Use App Password, not normal password
TO_EMAIL = "acchiyammabalijepalli@gmail.com"

# Create email
msg = MIMEText("Hi,\n\nThis is a test email from Python.\n\nThanks!")
msg["Subject"] = "Test Mail"
msg["From"] = SENDER_EMAIL
msg["To"] = TO_EMAIL

# Send email
with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
    server.starttls()
    server.login(SENDER_EMAIL, SENDER_PASSWORD)
    server.send_message(msg)

print("Email sent!")
