import os
import smtplib
from email.message import EmailMessage


def send_email_with_attachments(
    config,
    subject,
    body,
    to_email,
    attachments=None,
):
    if config.get("MAIL_SUPPRESS_SEND", True):
        return True

    host = config.get("MAIL_HOST")
    port = int(config.get("MAIL_PORT", 587))
    username = config.get("MAIL_USERNAME")
    password = config.get("MAIL_PASSWORD")
    sender = config.get("MAIL_DEFAULT_SENDER") or username
    use_tls = bool(config.get("MAIL_USE_TLS", True))

    if not host or not sender:
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email
    msg.set_content(body)

    for file_path in attachments or []:
        if not os.path.exists(file_path):
            continue
        with open(file_path, "rb") as fp:
            content = fp.read()
        msg.add_attachment(
            content,
            maintype="application",
            subtype="pdf",
            filename=os.path.basename(file_path),
        )

    with smtplib.SMTP(host, port) as smtp:
        if use_tls:
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(msg)
    return True
