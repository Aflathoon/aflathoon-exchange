BRAND = "Aflathoon Exchange"


def _wrap_html(title, body_html):
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#0b0f1e;font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#e8ecf6">
  <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#0b0f1e;padding:32px 0">
    <tr><td align="center">
      <table role="presentation" cellpadding="0" cellspacing="0" width="560" style="background:#141a33;border-radius:14px;border:1px solid #222a4a">
        <tr><td style="padding:28px 32px 12px">
          <div style="font-size:1.2rem;font-weight:800;color:#6f8cff">{BRAND}</div>
        </td></tr>
        <tr><td style="padding:8px 32px 32px">
          <h1 style="font-size:1.4rem;color:#fff;margin:0 0 16px">{title}</h1>
          <div style="color:#cbd5e1;line-height:1.65;font-size:15px">{body_html}</div>
          <hr style="border:0;border-top:1px solid #222a4a;margin:24px 0">
          <div style="color:#8892b0;font-size:12px">If you didn't request this, ignore this email.</div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def verify_email(user, url):
    text = f"""Hi {user.username},

Welcome to {BRAND}.

Please confirm your email address by clicking the link below:

{url}

This link expires in 48 hours.

- {BRAND}
"""
    html = _wrap_html(
        "Confirm your email",
        f"""<p>Hi <strong>{user.username}</strong>,</p>
            <p>Welcome to {BRAND}. Please confirm your email address to activate your account.</p>
            <p style="margin:24px 0"><a href="{url}" style="background:#6f8cff;color:#fff;padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:600;display:inline-block">Confirm email</a></p>
            <p style="color:#8892b0;font-size:13px">Or copy: <span style="color:#6f8cff;word-break:break-all">{url}</span></p>"""
    )
    return text, html


def password_reset(user, url):
    text = f"""Hi {user.username},

A password reset was requested for your {BRAND} account.

Reset your password by clicking this link:

{url}

This link expires in 1 hour and can only be used once.

- {BRAND}
"""
    html = _wrap_html(
        "Reset your password",
        f"""<p>Hi <strong>{user.username}</strong>,</p>
            <p>A password reset was requested for your {BRAND} account.</p>
            <p style="margin:24px 0"><a href="{url}" style="background:#6f8cff;color:#fff;padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:600;display:inline-block">Reset password</a></p>
            <p style="color:#8892b0;font-size:13px">Or copy: <span style="color:#6f8cff;word-break:break-all">{url}</span></p>"""
    )
    return text, html
