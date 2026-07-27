from pathlib import Path
import re


def replace_once(text: str, pattern: str, replacement: str, label: str, flags: int = 0) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f"Unable to apply CamCore branding replacement: {label}")
    return updated


# Main Tautulli interface: dark navigation bar, therefore use the dark-background logo.
base_path = Path("/app/tautulli/data/interfaces/default/base.html")
base = base_path.read_text(encoding="utf-8-sig")
base = replace_once(base, r"<title>.*?</title>", r"<title>CamCore Media Insights - ${title} | ${server_name}</title>", "main browser title")
base = replace_once(base, r'<meta name="description" content="[^"]*">', '<meta name="description" content="CamCore Media Insights — private Plex monitoring and analytics.">', "main description")
base = replace_once(
    base,
    r"<!-- Favicons -->.*?<!-- ICONS -->",
    '''<!-- Favicons -->
    <link rel="icon" type="image/svg+xml" href="${http_root}images/favicon/camcore-icon.svg">
    <link rel="shortcut icon" href="${http_root}images/favicon/camcore-icon.svg">

    <!-- ICONS -->''',
    "main favicon block",
    re.S,
)
base = base.replace('<meta name="apple-mobile-web-app-title" content="Tautulli">', '<meta name="apple-mobile-web-app-title" content="CamCore Media Insights">')
base = base.replace('<meta name="application-name" content="Tautulli">', '<meta name="application-name" content="CamCore Media Insights">')
base = replace_once(
    base,
    r'<a class="navbar-brand" href="home" title="[^"]*">\s*<img[^>]+>\s*</a>',
    '''<a class="navbar-brand" href="home" title="CamCore Media Insights">
                    <img src="${http_root}images/camcore-logo-dark.png" height="38" alt="CamCore — Cameron Family Secure Network" style="max-width: 190px; width: auto; object-fit: contain;">
                </a>''',
    "navbar logo",
    re.S,
)
base_path.write_text(base, encoding="utf-8")


# Tautulli sign-in page: dark background, therefore use the dark-background logo.
login_path = Path("/app/tautulli/data/interfaces/default/login.html")
login = login_path.read_text(encoding="utf-8-sig")
login = replace_once(login, r"<title>.*?</title>", r"<title>CamCore Media Insights - ${title}</title>", "login browser title")
login = replace_once(login, r'<meta name="description" content="[^"]*">', '<meta name="description" content="Private CamCore Plex monitoring and analytics sign-in.">', "login description")
login = replace_once(
    login,
    r"<!-- Favicons -->.*?<!-- ICONS -->",
    '''<!-- Favicons -->
    <link rel="icon" type="image/svg+xml" href="${http_root}images/favicon/camcore-icon.svg">
    <link rel="shortcut icon" href="${http_root}images/favicon/camcore-icon.svg">

    <!-- ICONS -->''',
    "login favicon block",
    re.S,
)
login = login.replace('<meta name="apple-mobile-web-app-title" content="Tautulli">', '<meta name="apple-mobile-web-app-title" content="CamCore Media Insights">')
login = login.replace('<meta name="application-name" content="Tautulli">', '<meta name="application-name" content="CamCore Media Insights">')
login = replace_once(
    login,
    r'<div class="login-logo">\s*<img[^>]+>\s*</div>',
    '''<div class="login-logo">
                    <img src="${http_root}images/camcore-logo-dark.png" height="110" alt="CamCore — Cameron Family Secure Network" style="max-width: 360px; width: auto; object-fit: contain;">
                </div>''',
    "login logo",
    re.S,
)
login_path.write_text(login, encoding="utf-8")


# Newsletter password page: Tautulli styling is dark, so use the dark-background logo.
auth_path = Path("/app/tautulli/data/interfaces/default/newsletter_auth.html")
auth = auth_path.read_text(encoding="utf-8-sig")
auth = replace_once(auth, r"<title>.*?</title>", r"<title>CamCore Media Newsletter - ${title}</title>", "newsletter auth title")
auth = replace_once(
    auth,
    r'<div class="newsletter-logo">\s*<img[^>]+>\s*</div>',
    '''<div class="newsletter-logo">
                    <img src="${http_root}images/camcore-logo-dark.png" height="100" alt="CamCore — Cameron Family Secure Network" style="max-width: 360px; width: auto; object-fit: contain;">
                </div>''',
    "newsletter auth logo",
    re.S,
)
auth_path.write_text(auth, encoding="utf-8")


# Recently Added newsletters use a fixed dark #282A2D background.
# Use the locally hosted copy when Tautulli image hosting is enabled, with a
# public raw-GitHub fallback for email clients outside the CamCore network.
public_dark_logo = "https://raw.githubusercontent.com/camcoreau/tautulli/master/camcore-branding/generated/camcore-logo-dark.png"

for newsletter_name in ("recently_added.html", "recently_added.internal.html"):
    newsletter_path = Path("/app/tautulli/data/interfaces/newsletters") / newsletter_name
    if not newsletter_path.exists():
        continue

    newsletter = newsletter_path.read_text(encoding="utf-8-sig")
    newsletter = replace_once(newsletter, r"<title>.*?</title>", r"<title>CamCore Media Newsletter - ${subject}</title>", f"{newsletter_name} title")
    newsletter = re.sub(r">Tautulli Newsletter\s*-\s*\$\{subject\}<", r">CamCore Media Newsletter - ${subject}<", newsletter, count=1)
    newsletter = replace_once(
        newsletter,
        r'<img[^>]+class="header-img"[^>]*>',
        f'''<img src="${{base_url_image + 'images/camcore-logo-dark.png' if base_url_image else '{public_dark_logo}'}}" class="header-img" width="520" height="144" alt="CamCore — Cameron Family Secure Network" style="border: none; -ms-interpolation-mode: bicubic; max-width: 100%; width: 520px; height: auto; margin: 0 auto; display: block;">''',
        f"{newsletter_name} header logo",
    )
    newsletter = newsletter.replace(
        ".header {\n            width: 100%;\n            height: 90px;",
        ".header {\n            width: 100%;\n            height: 145px;",
    )
    newsletter = re.sub(
        r"\.header-img \{.*?\}",
        ".header-img {\n            width: 520px;\n            height: auto;\n            margin: 0 auto;\n        }",
        newsletter,
        count=1,
        flags=re.S,
    )
    newsletter = newsletter.replace(
        "table[class=body] .header {\n                height: 75px !important;\n            }",
        "table[class=body] .header {\n                height: auto !important;\n            }",
    )
    newsletter = re.sub(
        r"table\[class=body\] \.header-img \{.*?\}",
        "table[class=body] .header-img {\n                width: 410px !important;\n                height: auto !important;\n                margin: 0 auto !important;\n            }",
        newsletter,
        count=1,
        flags=re.S,
    )
    newsletter_path.write_text(newsletter, encoding="utf-8")
