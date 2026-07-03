from tools.email.gmail_client import GmailClient

gmail = GmailClient()

gmail.send_email(

    to="YOUR_EMAIL@gmail.com",

    subject="Mike Test",

    body="Hello from Mike 🚀"

)

print("Email sent!")