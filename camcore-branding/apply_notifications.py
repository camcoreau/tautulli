from pathlib import Path
import os


ROOT = Path(os.environ.get("CAMCORE_TAUTULLI_ROOT", "/app/tautulli"))


def replace_text_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"Unable to apply CamCore notification replacement: {label} (found {count})"
        )
    return text.replace(old, new, 1)


LEGACY_ACTION_TEXT = {
    "on_play": ("Tautulli ({server_name})", "{user} ({player}) started playing {title}."),
    "on_stop": ("Tautulli ({server_name})", "{user} ({player}) has stopped {title}."),
    "on_pause": ("Tautulli ({server_name})", "{user} ({player}) has paused {title}."),
    "on_resume": ("Tautulli ({server_name})", "{user} ({player}) has resumed {title}."),
    "on_error": ("Tautulli ({server_name})", "{user} ({player}) encountered an error trying to play {title}."),
    "on_change": ("Tautulli ({server_name})", "{user} ({player}) has changed transcode decision for {title}."),
    "on_intro": ("Tautulli ({server_name})", "{user} ({player}) has reached an intro marker for {title}."),
    "on_commercial": ("Tautulli ({server_name})", "{user} ({player}) has reached a commercial marker for {title}."),
    "on_credits": ("Tautulli ({server_name})", "{user} ({player}) has reached a credits marker for {title}."),
    "on_watched": ("Tautulli ({server_name})", "{user} ({player}) has watched {title}."),
    "on_buffer": ("Tautulli ({server_name})", "{user} ({player}) is buffering {title}."),
    "on_concurrent": ("Tautulli ({server_name})", "{user} has {user_streams} concurrent streams."),
    "on_newdevice": ("Tautulli ({server_name})", "{user} is streaming from a new device: {player}."),
    "on_created": ("Tautulli ({server_name})", "{title} was recently added to Plex."),
    "on_intdown": ("Tautulli ({server_name})", "The Plex Media Server is down."),
    "on_intup": ("Tautulli ({server_name})", "The Plex Media Server is back up."),
    "on_extdown": ("Tautulli ({server_name})", "The Plex Media Server remote access is down. ({remote_access_reason})"),
    "on_extup": ("Tautulli ({server_name})", "The Plex Media Server remote access is back up."),
    "on_pmsupdate": ("Tautulli ({server_name})", "An update is available for the Plex Media Server (version {update_version})."),
    "on_plexpyupdate": ("Tautulli ({server_name})", "An update is available for Tautulli (version {tautulli_update_version})."),
    "on_plexpydbcorrupt": ("Tautulli ({server_name})", "Tautulli database corruption detected. Automatic cleanup of database backups is suspended."),
    "on_tokenexpired": ("Tautulli ({server_name})", "The Tautulli Plex account token has expired."),
}

CAMCORE_ACTION_TEXT = {
    "on_play": ("Playback started — {title}", "{user} started playing {title} on {player}."),
    "on_stop": ("Playback stopped — {title}", "{user} stopped playing {title} on {player}."),
    "on_pause": ("Playback paused — {title}", "{user} paused {title} on {player}."),
    "on_resume": ("Playback resumed — {title}", "{user} resumed {title} on {player}."),
    "on_error": ("Playback issue detected — {title}", "A playback error was detected for {user} while using {player} to play {title}."),
    "on_change": ("Playback mode changed — {title}", "{user}'s playback of {title} on {player} changed to {transcode_decision}."),
    "on_intro": ("Intro reached — {title}", "{user} reached an intro marker while playing {title}."),
    "on_commercial": ("Commercial marker reached — {title}", "{user} reached a commercial marker while playing {title}."),
    "on_credits": ("Credits reached — {title}", "{user} reached the credits while playing {title}."),
    "on_watched": ("Completion threshold reached — {title}", "{user} reached the watched or listened threshold for {title}."),
    "on_buffer": ("Buffering detected — {title}", "Buffering was detected for {user} while playing {title} on {player}."),
    "on_concurrent": ("Concurrent streams detected — {user}", "{user} now has {user_streams} concurrent streams on Cameron-Media."),
    "on_newdevice": ("New playback device — {user}", "{user} started streaming from a new device: {player}."),
    "on_created": ("New on Cameron-Media — {title}", "{title} has been added and is now available on Cameron-Media."),
    "on_intdown": ("Cameron-Media is unavailable", "Cameron-Media cannot currently be reached by CamCore Media Insights. CamCore Operations may need to investigate."),
    "on_intup": ("Cameron-Media is back online", "Cameron-Media is reachable again and monitoring has resumed."),
    "on_extdown": ("Cameron-Media remote access is unavailable", "Remote access to Cameron-Media is currently unavailable. {remote_access_reason}"),
    "on_extup": ("Cameron-Media remote access restored", "Remote access to Cameron-Media is available again."),
    "on_pmsupdate": ("Plex Media Server update available", "A Plex Media Server update is available for Cameron-Media: version {update_version}."),
    "on_plexpyupdate": ("Media Insights update available", "A Tautulli update is available for CamCore Media Insights: version {tautulli_update_version}."),
    "on_plexpydbcorrupt": ("Media Insights database issue detected", "CamCore Media Insights detected Tautulli database corruption. Automatic database-backup cleanup has been suspended and CamCore Operations should investigate."),
    "on_tokenexpired": ("Media Insights lost Plex access", "The Plex account token used by CamCore Media Insights has expired. Re-authentication is required to restore monitoring."),
}

EVENT_LABELS = {
    "play": "PLAYBACK STARTED",
    "stop": "PLAYBACK STOPPED",
    "pause": "PLAYBACK PAUSED",
    "resume": "PLAYBACK RESUMED",
    "error": "PLAYBACK ISSUE",
    "change": "PLAYBACK MODE",
    "intro": "INTRO MARKER",
    "commercial": "COMMERCIAL MARKER",
    "credits": "CREDITS MARKER",
    "watched": "COMPLETION",
    "buffer": "BUFFERING",
    "concurrent": "CONCURRENT STREAMS",
    "newdevice": "NEW DEVICE",
    "created": "NEW MEDIA",
    "intdown": "SERVICE ALERT",
    "intup": "SERVICE RESTORED",
    "extdown": "REMOTE ACCESS",
    "extup": "REMOTE ACCESS RESTORED",
    "pmsupdate": "UPDATE AVAILABLE",
    "plexpyupdate": "UPDATE AVAILABLE",
    "plexpydbcorrupt": "DATABASE ALERT",
    "tokenexpired": "AUTHENTICATION ALERT",
    "test": "TEST NOTIFICATION",
    "api": "MEDIA INSIGHTS",
}


notifiers_path = ROOT / "plexpy" / "notifiers.py"
notifiers = notifiers_path.read_text(encoding="utf-8-sig")
notifiers = replace_text_once(
    notifiers,
    "from email.mime.multipart import MIMEMultipart\nfrom email.mime.text import MIMEText\nimport email.utils\n",
    "from email.mime.image import MIMEImage\nfrom email.mime.multipart import MIMEMultipart\nfrom email.mime.text import MIMEText\nimport email.utils\nimport html as html_lib\n",
    "email MIME imports",
)

constants_marker = "DEFAULT_CUSTOM_CONDITIONS = [{'parameter': '', 'operator': '', 'value': [], 'type': None}]\n"
constants_block = constants_marker + f"""
CAMCORE_EMAIL_LOGO_CID = 'camcore-media-insights-logo'
CAMCORE_EMAIL_LOGO_PATH = os.path.join(plexpy.PROG_DIR, 'data', 'interfaces', 'default', 'images', 'camcore-logo-dark.png')
CAMCORE_EMAIL_DEFAULTS = {CAMCORE_ACTION_TEXT!r}
CAMCORE_EMAIL_LEGACY_DEFAULTS = {LEGACY_ACTION_TEXT!r}
CAMCORE_EMAIL_EVENT_LABELS = {EVENT_LABELS!r}


def _camcore_effective_sender_name(from_name):
    if from_name in ('', 'Tautulli'):
        return 'Insights | CamCore Media'
    if from_name == 'Tautulli Newsletter':
        return 'Updates | CamCore Media'
    return from_name


def _camcore_notification_html(subject, body, action):
    subject_html = html_lib.escape(subject or 'CamCore Media Insights notification')
    body_html = body if '<' in body and '>' in body else html_lib.escape(body or '').replace('\\n', '<br>')
    event_label = CAMCORE_EMAIL_EVENT_LABELS.get(action, 'MEDIA INSIGHTS')
    application_url = helpers.get_plexpy_url() or ''
    button_html = ''
    if application_url:
        escaped_url = html_lib.escape(application_url, quote=True)
        button_html = f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0 0;"><tr><td bgcolor="#11bdd4" style="border-radius:7px;"><a href="{{escaped_url}}" style="display:inline-block;padding:13px 20px;color:#05202a;font-size:15px;line-height:20px;font-weight:700;text-decoration:none;border-radius:7px;">Open Media Insights</a></td></tr></table>'
    if os.path.exists(CAMCORE_EMAIL_LOGO_PATH):
        brand_html = f'<img src="cid:{{CAMCORE_EMAIL_LOGO_CID}}" alt="CamCore — Cameron Family Secure Network" width="310" style="display:block;width:310px;max-width:100%;height:auto;">'
    else:
        brand_html = '<div style="color:#ffffff;font-size:32px;font-weight:800;">CamCore</div>'
    return f'''<!doctype html><html lang="en-AU"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;padding:0;background:#edf3f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#10212b;"><table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#edf3f6;width:100%;"><tr><td align="center" style="padding:34px 12px;"><table role="presentation" cellpadding="0" cellspacing="0" border="0" width="640" style="width:640px;max-width:640px;margin:0 auto;"><tr><td style="padding:22px 32px 18px;background:#071827;border-radius:12px 12px 0 0;">{{brand_html}}<div style="margin-top:14px;color:#a9bbc6;font-size:10px;line-height:15px;font-weight:700;letter-spacing:1.8px;">CAMCORE MEDIA • INSIGHTS</div></td></tr><tr><td style="height:4px;line-height:4px;font-size:0;background:#12c4de;">&nbsp;</td></tr><tr><td style="padding:36px 32px 32px;background:#ffffff;"><table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 16px;"><tr><td style="padding:5px 10px;background:#eefbfd;border:1px solid #b8e8ef;border-radius:999px;color:#0d879b;font-size:10px;line-height:13px;font-weight:800;letter-spacing:1.2px;">{{event_label}}</td></tr></table><h1 style="margin:0;color:#071827;font-size:31px;line-height:38px;font-weight:800;letter-spacing:-0.55px;">{{subject_html}}</h1><p style="margin:18px 0 0;color:#435562;font-size:15px;line-height:24px;">{{body_html}}</p><table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:24px 0 0;"><tr><td style="padding:18px 20px;background:#f1f6f8;border:1px solid #d8e4e9;border-radius:9px;color:#10212b;"><div style="margin:0 0 8px;color:#718391;font-size:10px;line-height:14px;font-weight:750;letter-spacing:1.4px;">MONITORING SERVICE</div><div style="color:#071827;font-size:15px;line-height:22px;font-weight:750;">CamCore Media Insights</div><div style="margin-top:5px;color:#526572;font-size:13px;line-height:20px;">Monitoring and analytics for Cameron-Media.</div></td></tr></table>{{button_html}}</td></tr><tr><td style="padding:24px 32px 26px;background:#f8fafb;border-top:1px solid #e2eaee;border-radius:0 0 12px 12px;text-align:center;"><div style="color:#10212b;font-size:13px;line-height:18px;font-weight:750;">CamCore Media Insights</div><div style="margin-top:2px;color:#718391;font-size:11px;line-height:16px;">Cameron Family Secure Network</div><div style="margin-top:12px;font-size:12px;line-height:19px;"><a href="https://plex.camcore.au/" style="color:#0d879b;font-weight:650;text-decoration:none;">Cameron-Media</a>&nbsp;&nbsp;•&nbsp;&nbsp;<a href="https://status.camcore.au/" style="color:#0d879b;font-weight:650;text-decoration:none;">Service Status</a>&nbsp;&nbsp;•&nbsp;&nbsp;<a href="https://camcore.au/support.html" style="color:#0d879b;font-weight:650;text-decoration:none;">CamCore Support</a></div><div style="margin-top:4px;font-size:12px;line-height:18px;"><a href="mailto:help@camcore.au" style="color:#0d879b;font-weight:650;text-decoration:none;">help@camcore.au</a></div></td></tr></table></td></tr></table></body></html>'''

"""
notifiers = replace_text_once(notifiers, constants_marker, constants_block, "CamCore email constants")

notifiers = replace_text_once(
    notifiers,
    '''            if body is None:
                body = "" if result['agent_name'] in ('scripts', 'webhook') else notify_actions[k]['body']

            notifier_actions[k] = helpers.cast_to_int(result.pop(k))
''',
    '''            if body is None:
                body = "" if result['agent_name'] in ('scripts', 'webhook') else notify_actions[k]['body']

            if result['agent_name'] == 'email' and k in CAMCORE_EMAIL_DEFAULTS:
                legacy_subject, legacy_body = CAMCORE_EMAIL_LEGACY_DEFAULTS[k]
                camcore_subject, camcore_body = CAMCORE_EMAIL_DEFAULTS[k]
                if subject == legacy_subject:
                    subject = camcore_subject
                if body == legacy_body:
                    body = camcore_body

            notifier_actions[k] = helpers.cast_to_int(result.pop(k))
''',
    "legacy email default upgrade",
)

notifiers = replace_text_once(
    notifiers,
    '''        if self.config['html_support']:
            plain = MIMEText(None, 'plain', 'utf-8')
            plain.replace_header('Content-Transfer-Encoding', 'quoted-printable')
            plain.set_payload(kwargs.get('plaintext', bleach.clean(body, strip=True)), 'utf-8')

            html = MIMEText(body, 'html', 'utf-8')

            msg = MIMEMultipart('alternative')
            msg.attach(plain)
            msg.attach(html)
        else:
            msg = MIMEText(None, 'plain', 'utf-8')
            msg.replace_header('Content-Transfer-Encoding', 'quoted-printable')
            msg.set_payload(body, 'utf-8')
''',
    '''        if action in ('test', 'api'):
            if subject == 'Tautulli':
                subject = 'CamCore Media Insights test notification'
            if body == 'Test Notification':
                body = 'This test confirms that CamCore Media Insights can deliver notifications successfully.'

        if self.config['html_support']:
            plaintext_body = kwargs.get('plaintext', bleach.clean(body, strip=True))
            if action:
                body = _camcore_notification_html(subject, body, action)

            plain = MIMEText(None, 'plain', 'utf-8')
            plain.replace_header('Content-Transfer-Encoding', 'quoted-printable')
            plain.set_payload(plaintext_body, 'utf-8')

            html = MIMEText(body, 'html', 'utf-8')
            alternative = MIMEMultipart('alternative')
            alternative.attach(plain)
            alternative.attach(html)

            if action and os.path.exists(CAMCORE_EMAIL_LOGO_PATH):
                msg = MIMEMultipart('related')
                msg.attach(alternative)
                with open(CAMCORE_EMAIL_LOGO_PATH, 'rb') as logo_file:
                    logo = MIMEImage(logo_file.read(), _subtype='png')
                logo.add_header('Content-ID', '<{}>'.format(CAMCORE_EMAIL_LOGO_CID))
                logo.add_header('Content-Disposition', 'inline', filename='camcore-logo.png')
                msg.attach(logo)
            else:
                msg = alternative
        else:
            msg = MIMEText(None, 'plain', 'utf-8')
            msg.replace_header('Content-Transfer-Encoding', 'quoted-printable')
            msg.set_payload(body, 'utf-8')
''',
    "HTML email renderer",
)

notifiers = replace_text_once(
    notifiers,
    '''        msg['Subject'] = subject
        msg['From'] = email.utils.formataddr((self.config['from_name'], self.config['from']))
        msg['To'] = ','.join(self.config['to'])
''',
    '''        msg['Subject'] = subject
        sender_name = _camcore_effective_sender_name(self.config['from_name'])
        msg['From'] = email.utils.formataddr((sender_name, self.config['from']))
        if self.config['from']:
            msg['Reply-To'] = self.config['from']
        msg['To'] = ','.join(self.config['to'])
''',
    "CamCore sender identity",
)

notifiers = replace_text_once(
    notifiers,
    "_DEFAULT_CONFIG = {'from_name': 'Tautulli',",
    "_DEFAULT_CONFIG = {'from_name': 'Insights | CamCore Media',",
    "Email default sender name",
)
notifiers_path.write_text(notifiers, encoding="utf-8")


newsletters_path = ROOT / "plexpy" / "newsletters.py"
newsletters = newsletters_path.read_text(encoding="utf-8-sig")
newsletters = replace_text_once(
    newsletters,
    "_DEFAULT_EMAIL_CONFIG['from_name'] = 'Tautulli Newsletter'",
    "_DEFAULT_EMAIL_CONFIG['from_name'] = 'Updates | CamCore Media'",
    "newsletter sender name",
)
newsletters = replace_text_once(
    newsletters,
    "_DEFAULT_SUBJECT = 'Tautulli Newsletter'\n    _DEFAULT_BODY = 'View the newsletter here: {newsletter_url}'",
    "_DEFAULT_SUBJECT = \"What's new on Cameron-Media — {end_date}\"\n    _DEFAULT_BODY = 'View this Cameron-Media update in your browser: {newsletter_url}'",
    "base newsletter defaults",
)
newsletters = replace_text_once(
    newsletters,
    "_DEFAULT_SUBJECT = 'Recently Added to {server_name}! ({end_date})'\n    _DEFAULT_BODY = 'View the newsletter here: {newsletter_url}'",
    "_DEFAULT_SUBJECT = \"What's new on Cameron-Media — {end_date}\"\n    _DEFAULT_BODY = 'View this Cameron-Media update in your browser: {newsletter_url}'",
    "recently added newsletter defaults",
)
newsletters = replace_text_once(
    newsletters,
    '''        self.subject = subject or self._DEFAULT_SUBJECT
        self.body = body or self._DEFAULT_BODY
        self.message = message or self._DEFAULT_MESSAGE
''',
    '''        self.subject = subject or self._DEFAULT_SUBJECT
        self.body = body or self._DEFAULT_BODY
        self.message = message or self._DEFAULT_MESSAGE

        if self.subject in ('Tautulli Newsletter', 'Recently Added to {server_name}! ({end_date})'):
            self.subject = "What's new on Cameron-Media — {end_date}"
        if self.body == 'View the newsletter here: {newsletter_url}':
            self.body = 'View this Cameron-Media update in your browser: {newsletter_url}'
        if self.email_config.get('from_name') == 'Tautulli Newsletter':
            self.email_config['from_name'] = 'Updates | CamCore Media'
''',
    "legacy newsletter defaults",
)
newsletters_path.write_text(newsletters, encoding="utf-8")

# The existing CamCore branding script adds the visible weekly-update title. Keep
# the hidden/preheader title from repeating the same phrase once the subject is
# also CamCore-standardised.
for template_name in ("recently_added.html", "recently_added.internal.html"):
    template_path = ROOT / "data" / "interfaces" / "newsletters" / template_name
    if template_path.exists():
        template = template_path.read_text(encoding="utf-8-sig")
        template = template.replace(
            "New this week on Cameron-Media — ${subject}",
            "${subject}",
        )
        template_path.write_text(template, encoding="utf-8")

print("CamCore Media Insights notification and newsletter standards applied.")
