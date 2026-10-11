import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr


def _env_bool(name, default=False):
    v = os.getenv(name, str(default)).lower()
    return v in ('1', 'true', 'yes', 'on')


def _parse_from():
    raw = os.getenv('EMAIL_FROM', 'Aflathoon <noreply@localhost>')
    name = os.getenv('EMAIL_FROM_NAME', 'Aflathoon Exchange')
    if '<' in raw and '>' in raw:
        left, right = raw.split('<', 1)
        addr = right.split('>', 1)[0].strip()
        if left.strip():
            name = left.strip()
    else:
        addr = raw.strip()
    return name, addr


def send_email(to_addr, subject, body_text, body_html=None, reply_to=None):
    backend = os.getenv('EMAIL_BACKEND', 'console').lower().strip()
    if backend == 'console':
        _print_to_console(to_addr, subject, body_text, body_html)
        return True
    if backend == 'smtp':
        return _send_smtp(to_addr, subject, body_text, body_html, reply_to)
    raise RuntimeError(f"Unknown EMAIL_BACKEND: {backend!r}")


def _print_to_console(to_addr, subject, body_text, body_html):
    bar = '=' * 72
    print()
    print(bar)
    print(f"  [EMAIL] To:      {to_addr}")
    print(f"  [EMAIL] Subject: {subject}")
    print(bar)
    print(body_text)
    if body_html:
        print('-' * 72)
        print('  HTML version (truncated to 500 chars)')
        print(body_html[:500] + ('...' if len(body_html) > 500 else ''))
    print(bar)
    print()


def _send_smtp(to_addr, subject, body_text, body_html, reply_to):
    host = os.getenv('SMTP_HOST', '').strip()
    if not host:
        raise RuntimeError('SMTP_HOST not set but EMAIL_BACKEND=smtp')
    port = int(os.getenv('SMTP_PORT', '587'))
    user = os.getenv('SMTP_USER', '').strip()
    pwd  = os.getenv('SMTP_PASS', '').strip()
    use_tls = _env_bool('SMTP_USE_TLS', True)
    from_name, from_addr = _parse_from()

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = formataddr((from_name, from_addr))
    msg['To'] = to_addr
    if reply_to:
        msg['Reply-To'] = reply_to
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype='html')

    if use_tls:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls(context=ctx)
            if user:
                s.login(user, pwd)
            s.send_message(msg)
    else:
        with smtplib.SMTP_SSL(host, port, timeout=15) as s:
            if user:
                s.login(user, pwd)
            s.send_message(msg)
    return True
