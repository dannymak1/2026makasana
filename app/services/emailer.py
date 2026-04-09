import os
import smtplib
from email.message import EmailMessage
from html import escape
from urllib.parse import urljoin


def build_branded_email_html(config, heading, intro_text, content_html, footer_note=None):
    site_url = (config.get("SITE_URL") or "https://www.makasanaconsultancy.com").strip()
    if not site_url.startswith("http://") and not site_url.startswith("https://"):
        site_url = f"https://{site_url}"
    logo_url = urljoin(site_url.rstrip("/") + "/", "static/assets/images/makasana-consultancy-logo.png")
    safe_heading = escape(heading or "Makasana Consultancy")
    safe_intro = escape(intro_text or "")
    safe_footer_note = escape(footer_note or "This is an automated message from Makasana Consultancy.")

    return f"""\
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{safe_heading}</title>
  </head>
  <body style="margin:0; padding:0; background:#f2f6f2; font-family:Arial, Helvetica, sans-serif; color:#173c35;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f2f6f2; padding:24px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:680px; background:#ffffff; border:1px solid #d8e5db; border-radius:14px; overflow:hidden;">
            <tr>
              <td style="background:linear-gradient(120deg,#e7f2e7 0%,#d4ebb9 100%); padding:20px 24px; border-bottom:1px solid #d8e5db;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                  <tr>
                    <td valign="middle" style="padding-right:12px;">
                      <a href="{site_url}" target="_blank" rel="noopener noreferrer" style="text-decoration:none;">
                        <img src="{logo_url}" alt="Makasana Consultancy" style="max-width:210px; height:auto; display:block; border:0;">
                      </a>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:24px;">
                <h2 style="margin:0 0 10px 0; font-size:24px; line-height:1.3; color:#0f2f2f;">{safe_heading}</h2>
                <p style="margin:0 0 18px 0; font-size:14px; line-height:1.7; color:#355c54;">{safe_intro}</p>
                <div style="font-size:14px; line-height:1.8; color:#1f3f39;">
                  {content_html}
                </div>
              </td>
            </tr>
            <tr>
              <td style="padding:16px 24px; border-top:1px solid #e3eee4; background:#fafdf8;">
                <p style="margin:0; font-size:12px; line-height:1.7; color:#57736c;">
                  {safe_footer_note}<br>
                  Makasana Consultancy &middot; Strategic Solutions for Growth
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def send_email_with_attachments(
    config,
    subject,
    body,
    to_email,
    attachments=None,
    html_body=None,
):
    if config.get("MAIL_SUPPRESS_SEND", True):
        return True

    host = config.get("MAIL_HOST")
    port = int(config.get("MAIL_PORT", 587))
    username = config.get("MAIL_USERNAME")
    password = config.get("MAIL_PASSWORD")
    sender = config.get("MAIL_DEFAULT_SENDER") or username
    use_tls = bool(config.get("MAIL_USE_TLS", True))
    use_ssl = bool(config.get("MAIL_USE_SSL", False))

    if not host or not sender:
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

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

    smtp_client = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    try:
        with smtp_client(host, port) as smtp:
            if use_tls and not use_ssl:
                smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(msg)
        return True
    except Exception:
        return False
