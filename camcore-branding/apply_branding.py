from pathlib import Path
import re


def replace_once(text: str, pattern: str, replacement: str, label: str, flags: int = 0) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f"Unable to apply CamCore branding replacement: {label}")
    return updated


def replace_text_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Unable to apply CamCore branding replacement: {label}")
    return text.replace(old, new, 1)


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


# Recently Added newsletters use a fixed dark background. Keep the working
# CamCore logo, then transform the default Tautulli email into a polished
# Cameron-Media weekly update.
public_dark_logo = "https://raw.githubusercontent.com/camcoreau/tautulli/master/camcore-branding/generated/camcore-logo-dark.png"
brand_teal = "#C8321A"
brand_teal_light = "#FF6A47"

newsletter_css = f'''

        /* -------------------------------------
            CAMCORE MEDIA NEWSLETTER
        ------------------------------------- */
        body,
        .body {{
            background-color: #0B1014 !important;
        }}
        .main {{
            background: #11181F !important;
            border: 1px solid #25313B !important;
            border-radius: 16px !important;
            overflow: hidden !important;
        }}
        .header {{
            padding-top: 20px !important;
        }}
        .camcore-kicker {{
            color: {brand_teal_light} !important;
            font-size: 12px !important;
            font-weight: 700 !important;
            letter-spacing: 2px !important;
            margin-top: 4px !important;
            text-align: center !important;
        }}
        .server-name {{
            font-size: 32px !important;
            font-weight: 700 !important;
            letter-spacing: -0.4px !important;
            margin-top: 5px !important;
        }}
        .dates {{
            color: #9FB0BF !important;
            font-size: 15px !important;
            margin-top: 5px !important;
        }}
        .camcore-intro {{
            color: #D7E0E7 !important;
            font-size: 16px !important;
            line-height: 1.6 !important;
            margin: 16px auto 8px !important;
            max-width: 680px !important;
            text-align: center !important;
        }}
        .camcore-actions {{
            margin: 20px auto 8px !important;
            max-width: 680px !important;
        }}
        .camcore-button {{
            border-radius: 8px !important;
            display: inline-block !important;
            font-size: 14px !important;
            font-weight: 700 !important;
            padding: 11px 18px !important;
            text-decoration: none !important;
        }}
        .body-message {{
            background: #17212A !important;
            border: 1px solid #2B3A46 !important;
            border-radius: 10px !important;
            box-sizing: border-box !important;
            color: #D7E0E7 !important;
            font-size: 16px !important;
            line-height: 1.6 !important;
            padding: 18px 22px !important;
        }}
        .sub-header-bar {{
            border-top-color: {brand_teal} !important;
            margin-bottom: 18px !important;
            width: 90px !important;
        }}
        .sub-header-title {{
            font-size: 27px !important;
            font-weight: 700 !important;
        }}
        .sub-header-count .count {{
            color: {brand_teal_light} !important;
            font-weight: 700 !important;
        }}
        .sub-header-count .count-units {{
            color: #9FB0BF !important;
            font-size: 15px !important;
            text-transform: none !important;
        }}
        .card-background {{
            background-color: #151E26 !important;
            border: 1px solid #2A3844 !important;
            border-radius: 10px !important;
            overflow: hidden !important;
        }}
        .card-poster {{
            background-color: #24313A !important;
        }}
        .card-info-title {{
            border-bottom-color: #31414E !important;
            font-size: 1rem !important;
            font-weight: 700 !important;
            padding: 9px !important;
        }}
        .card-info-body {{
            color: #D7E0E7 !important;
            line-height: 1.45 !important;
            padding: 9px !important;
        }}
        .badge {{
            background-color: #1D2933 !important;
            border: 1px solid #344653 !important;
            border-radius: 5px !important;
        }}
        .star-rating.full {{
            color: {brand_teal_light} !important;
        }}
        .footer-bar {{
            border-top-color: {brand_teal} !important;
        }}
        .camcore-footer {{
            color: #9FB0BF !important;
            line-height: 1.6 !important;
            margin: 0 auto !important;
            max-width: 720px !important;
            padding: 4px 20px 22px !important;
            text-align: center !important;
        }}
        .camcore-footer a {{
            color: {brand_teal_light} !important;
            font-weight: 700 !important;
            text-decoration: none !important;
        }}
        .view-full,
        .view-full a {{
            color: #9FB0BF !important;
        }}

        @media only screen and (max-width: 680px) {{
            table[class=body] .server-name {{
                font-size: 25px !important;
            }}
            table[class=body] .camcore-intro {{
                font-size: 14px !important;
                padding-left: 18px !important;
                padding-right: 18px !important;
            }}
            table[class=body] .camcore-actions td {{
                display: block !important;
                padding: 5px 18px !important;
                width: auto !important;
            }}
            table[class=body] .camcore-button {{
                box-sizing: border-box !important;
                display: block !important;
                width: 100% !important;
            }}
            table[class=body] .card-instance {{
                display: block !important;
                height: auto !important;
                max-width: 100% !important;
                min-width: 0 !important;
                padding: 5px !important;
                width: 100% !important;
            }}
            table[class=body] .card-instance.pad {{
                display: none !important;
            }}
            table[class=body] .card-poster-container {{
                height: 177px !important;
                min-width: 118px !important;
                width: 118px !important;
            }}
            table[class=body] .card-info-container {{
                height: 177px !important;
            }}
            table[class=body] .card-poster-overlay {{
                height: 175px !important;
                width: 116px !important;
            }}
            table[class=body] .card-info-title {{
                max-width: 205px !important;
            }}
            table[class=body] .card-info-body > p {{
                max-width: 205px !important;
            }}
        }}
'''

header_details_new = f'''<div class="camcore-kicker" style="color: {brand_teal_light};font-size: 12px;font-weight: 700;letter-spacing: 2px;margin-top: 4px;text-align: center;">CAMCORE MEDIA</div>
                            <div class="server-name" style="font-size: 32px;font-weight: 700;letter-spacing: -0.4px;margin-top: 5px;text-align: center;">What's new on Cameron-Media</div>
                            <div class="dates" style="color: #9FB0BF;font-size: 15px;margin-top: 5px;text-align: center;">Added ${{parameters['start_date']}} to ${{parameters['end_date']}}</div>
                            <div class="camcore-intro" style="color: #D7E0E7;font-size: 16px;line-height: 1.6;margin: 16px auto 8px;max-width: 680px;text-align: center;">Your weekly look at the latest movies, shows and episodes now available to watch on Cameron-Media.</div>
                            <table border="0" cellpadding="0" cellspacing="0" class="camcore-actions" style="border-collapse: separate;margin: 20px auto 8px;max-width: 680px;width: 100%;">
                                <tr>
                                    <td align="center" style="padding: 5px;width: 33.33%;"><a class="camcore-button" href="https://plex.camcore.au/" target="_blank" rel="noreferrer" style="background: {brand_teal};border-radius: 8px;color: #FFFFFF;display: inline-block;font-size: 14px;font-weight: 700;padding: 11px 18px;text-decoration: none;">Open Cameron-Media</a></td>
                                    <td align="center" style="padding: 5px;width: 33.33%;"><a class="camcore-button" href="https://requests.camcore.au/" target="_blank" rel="noreferrer" style="background: #22303B;border: 1px solid #3A4C59;border-radius: 8px;color: #FFFFFF;display: inline-block;font-size: 14px;font-weight: 700;padding: 10px 18px;text-decoration: none;">Request Something</a></td>
                                    <td align="center" style="padding: 5px;width: 33.33%;"><a class="camcore-button" href="https://status.camcore.au/" target="_blank" rel="noreferrer" style="background: #22303B;border: 1px solid #3A4C59;border-radius: 8px;color: #FFFFFF;display: inline-block;font-size: 14px;font-weight: 700;padding: 10px 18px;text-decoration: none;">System Status</a></td>
                                </tr>
                            </table>'''

footer_block = f'''<div class="camcore-footer" style="color: #9FB0BF;line-height: 1.6;margin: 0 auto;max-width: 720px;padding: 4px 20px 22px;text-align: center;">
                                    <p style="font-family: 'Open Sans', Helvetica, Arial, sans-serif;font-size: 13px;font-weight: 400;margin: 0 0 8px;">Looking for something else? <a href="https://requests.camcore.au/" target="_blank" rel="noreferrer" style="color: {brand_teal_light};font-weight: 700;text-decoration: none;">Request a movie or TV show</a>.</p>
                                    <p style="font-family: 'Open Sans', Helvetica, Arial, sans-serif;font-size: 13px;font-weight: 400;margin: 0 0 8px;"><a href="https://plex.camcore.au/" target="_blank" rel="noreferrer" style="color: {brand_teal_light};font-weight: 700;text-decoration: none;">Cameron-Media</a>&nbsp;&nbsp;•&nbsp;&nbsp;<a href="https://status.camcore.au/" target="_blank" rel="noreferrer" style="color: {brand_teal_light};font-weight: 700;text-decoration: none;">System Status</a>&nbsp;&nbsp;•&nbsp;&nbsp;<a href="https://camcore.au/support.html" target="_blank" rel="noreferrer" style="color: {brand_teal_light};font-weight: 700;text-decoration: none;">Get Support</a></p>
                                    <p style="font-family: 'Open Sans', Helvetica, Arial, sans-serif;font-size: 12px;font-weight: 400;margin: 0;color: #748592;">CamCore — Cameron Family Secure Network<br>This automated weekly update is generated by CamCore Media Insights.</p>
                                </div>
                                <!-- FOOTER MESSAGE - DO NOT REMOVE -->'''

for newsletter_name in ("recently_added.html", "recently_added.internal.html"):
    newsletter_path = Path("/app/tautulli/data/interfaces/newsletters") / newsletter_name
    if not newsletter_path.exists():
        continue

    newsletter = newsletter_path.read_text(encoding="utf-8-sig")
    newsletter = replace_once(newsletter, r"<title>.*?</title>", r"<title>${subject} | CamCore Media</title>", f"{newsletter_name} title")
    newsletter = re.sub(r">Tautulli Newsletter\s*-\s*\$\{subject\}<", r">New this week on Cameron-Media — ${subject}<", newsletter, count=1)
    newsletter = replace_once(
        newsletter,
        r'<img[^>]+class="header-img"[^>]*>',
        f'''<img src="${{base_url_image + 'images/camcore-logo-dark.png' if base_url_image else '{public_dark_logo}'}}" class="header-img" width="400" alt="CamCore — Cameron Family Secure Network" style="border: none; -ms-interpolation-mode: bicubic; max-width: 78%; width: 400px; height: auto; margin: 0 auto; display: block;">''',
        f"{newsletter_name} header logo",
    )
    newsletter = newsletter.replace(
        ".header {\n            width: 100%;\n            height: 90px;\n            text-align: center;\n        }",
        ".header {\n            width: 100%;\n            height: auto;\n            padding: 14px 0 8px;\n            text-align: center;\n        }",
    )
    newsletter = newsletter.replace(
        '<div class="header" style="width: 100%;height: 90px;text-align: center;">',
        '<div class="header" style="width: 100%;height: auto;text-align: center;padding: 14px 0 8px;">',
    )
    newsletter = re.sub(
        r"\.header-img \{.*?\}",
        ".header-img {\n            width: 400px;\n            max-width: 78%;\n            height: auto;\n            margin: 0 auto;\n        }",
        newsletter,
        count=1,
        flags=re.S,
    )
    newsletter = newsletter.replace(
        "table[class=body] .header {\n                height: 75px !important;\n            }",
        "table[class=body] .header {\n                height: auto !important;\n                padding: 10px 0 6px !important;\n            }",
    )
    newsletter = re.sub(
        r"table\[class=body\] \.header-img \{.*?\}",
        "table[class=body] .header-img {\n                width: 300px !important;\n                max-width: 82% !important;\n                height: auto !important;\n                margin: 0 auto !important;\n            }",
        newsletter,
        count=1,
        flags=re.S,
    )

    newsletter = replace_once(
        newsletter,
        r'<div class="server-name"[^>]*>\$\{parameters\[\'server_name\'\]\}</div>\s*<div class="dates"[^>]*>\$\{parameters\[\'start_date\'\]\} - \$\{parameters\[\'end_date\'\]\}</div>',
        header_details_new,
        f"{newsletter_name} CamCore header details",
    )
    newsletter = replace_text_once(newsletter, "<!-- FOOTER MESSAGE - DO NOT REMOVE -->", footer_block, f"{newsletter_name} CamCore footer")
    newsletter = replace_text_once(newsletter, "\n    </style>", newsletter_css + "\n    </style>", f"{newsletter_name} CamCore CSS")

    newsletter = newsletter.replace("Recently Added Movies", "New Movies")
    newsletter = newsletter.replace("Recently Added TV Shows", "New TV & Episodes")
    newsletter = newsletter.replace("Recently Added Music", "New Music")
    newsletter = newsletter.replace("Recently Added Videos", "New Videos")
    newsletter = newsletter.replace("Click here to view the full newsletter.", "View this update in your browser.")
    newsletter = newsletter.replace("#E5A00D", brand_teal)
    newsletter = newsletter.replace("#aaaaaa", "#9FB0BF")
    newsletter = newsletter.replace("background: #282A2D", "background: #11181F")
    newsletter = newsletter.replace("background-color: #282828", "background-color: #151E26")
    newsletter = newsletter.replace("background-color: #3F4245", "background-color: #24313A")
    newsletter = newsletter.replace("border-radius: 3px", "border-radius: 16px;border: 1px solid #25313B;overflow: hidden")

    newsletter_path.write_text(newsletter, encoding="utf-8")
