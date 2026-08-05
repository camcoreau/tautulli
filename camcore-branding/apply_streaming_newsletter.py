from pathlib import Path
import re


BRAND_TEAL = "#0091A0"
BRAND_TEAL_LIGHT = "#59CBD4"

STREAMING_CSS = f'''

        /* -------------------------------------
            CAMCORE STREAMING CATALOGUE
        ------------------------------------- */
        .camcore-featured-wrap {{
            padding: 10px 14px 18px !important;
        }}
        .camcore-featured {{
            background-color: #10171D !important;
            border: 1px solid #2B3944 !important;
            border-radius: 16px !important;
            overflow: hidden !important;
        }}
        .camcore-featured-art {{
            border: 0 !important;
            display: block !important;
            height: auto !important;
            line-height: 0 !important;
            max-width: 100% !important;
            width: 100% !important;
        }}
        .camcore-featured-copy {{
            background: #0B1014 !important;
            padding: 30px !important;
            text-align: left !important;
        }}
        .camcore-featured-kicker {{
            color: {BRAND_TEAL_LIGHT} !important;
            font-size: 12px !important;
            font-weight: 800 !important;
            letter-spacing: 2px !important;
            margin: 0 0 9px !important;
            text-transform: uppercase !important;
        }}
        .camcore-featured-title {{
            color: #FFFFFF !important;
            font-size: 34px !important;
            font-weight: 800 !important;
            letter-spacing: -0.7px !important;
            line-height: 1.08 !important;
            margin: 0 0 12px !important;
        }}
        .camcore-featured-meta {{
            color: #C0CDD6 !important;
            font-size: 13px !important;
            font-weight: 700 !important;
            line-height: 1.6 !important;
            margin: 0 0 13px !important;
        }}
        .camcore-featured-summary {{
            color: #D9E2E8 !important;
            font-size: 15px !important;
            line-height: 1.55 !important;
            margin: 0 0 20px !important;
            max-width: 620px !important;
        }}
        .camcore-watch-button {{
            background: {BRAND_TEAL} !important;
            border-radius: 8px !important;
            color: #FFFFFF !important;
            display: inline-block !important;
            font-size: 14px !important;
            font-weight: 800 !important;
            padding: 12px 22px !important;
            text-decoration: none !important;
        }}
        .sub-header-bar {{
            display: none !important;
        }}
        .sub-header-title {{
            font-size: 25px !important;
            font-weight: 800 !important;
            letter-spacing: -0.3px !important;
            margin-top: 24px !important;
            padding: 0 16px !important;
            text-align: left !important;
        }}
        .sub-header-title .sub-header-icon,
        .sub-header-icon {{
            display: none !important;
        }}
        .sub-header-count {{
            font-size: 15px !important;
            padding: 2px 16px 12px !important;
            text-align: left !important;
        }}
        .sub-header-count .count {{
            font-size: 15px !important;
        }}
        .sub-header-count .count-units {{
            font-size: 13px !important;
        }}
        .card-instance {{
            padding: 8px !important;
        }}
        .card-background {{
            border: 1px solid #2A3944 !important;
            border-radius: 14px !important;
            box-shadow: 0 8px 22px rgba(0, 0, 0, 0.28) !important;
            overflow: hidden !important;
        }}
        .card-poster {{
            border: 0 !important;
        }}
        .card-info-container {{
            background: rgba(11, 16, 20, 0.90) !important;
            padding-left: 0 !important;
        }}
        .card-info-title {{
            border-bottom: 0 !important;
            font-size: 17px !important;
            font-weight: 800 !important;
            line-height: 1.25 !important;
            padding: 13px 12px 7px !important;
        }}
        .card-info-body {{
            color: #CED9E0 !important;
            font-size: 12px !important;
            line-height: 1.45 !important;
            padding: 2px 12px 8px !important;
        }}
        .card-info-body p {{
            color: #CED9E0 !important;
        }}
        .card-info-footer {{
            padding: 4px 12px 12px !important;
        }}
        .badge {{
            background: #1C2831 !important;
            border: 1px solid #344651 !important;
            border-radius: 999px !important;
            color: #DCE5EA !important;
            margin-right: 5px !important;
            padding: 4px 8px !important;
        }}
        .star-rating.full {{
            color: {BRAND_TEAL_LIGHT} !important;
        }}
        .star-rating.empty {{
            color: #52626D !important;
        }}

        @media only screen and (max-width: 680px) {{
            table[class=body] .camcore-featured-wrap {{
                padding: 6px 5px 14px !important;
            }}
            table[class=body] .camcore-featured-copy {{
                padding: 24px 20px !important;
            }}
            table[class=body] .camcore-featured-title {{
                font-size: 27px !important;
            }}
            table[class=body] .camcore-featured-summary {{
                font-size: 14px !important;
            }}
            table[class=body] .camcore-watch-button {{
                box-sizing: border-box !important;
                text-align: center !important;
                width: 100% !important;
            }}
            table[class=body] .sub-header-title,
            table[class=body] .sub-header-count {{
                padding-left: 12px !important;
                padding-right: 12px !important;
            }}
            table[class=body] .card-info-title {{
                font-size: 16px !important;
                padding: 11px 10px 6px !important;
            }}
            table[class=body] .card-info-body {{
                padding: 2px 10px 6px !important;
            }}
            table[class=body] .card-info-footer {{
                padding: 3px 10px 10px !important;
            }}
        }}
'''

FEATURED_BLOCK = r'''
                    <%
                        featured_movies = recently_added.get('movie') or []
                        featured_shows = recently_added.get('show') or []

                        if featured_movies:
                            featured = featured_movies[0]
                            featured_kind = 'Movie'
                            recently_added['movie'] = featured_movies[1:]
                        elif featured_shows:
                            featured = featured_shows[0]
                            featured_kind = 'Series'
                            recently_added['show'] = featured_shows[1:]
                        else:
                            featured = None
                            featured_kind = None
                    %>
                    % if featured:
                    <tr class="camcore-featured-row">
                        <td class="camcore-featured-wrap" style="font-family: 'Open Sans', Helvetica, Arial, sans-serif;font-size: 14px;vertical-align: top;padding: 10px 14px 18px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" class="camcore-featured" style="background-color: #10171D;border: 1px solid #2B3944;border-radius: 16px;border-collapse: separate;overflow: hidden;width: 100%;">
                                <tr>
                                    <td style="font-family: 'Open Sans', Helvetica, Arial, sans-serif;font-size: 0;line-height: 0;vertical-align: top;">
                                        <a href="${parameters['pms_web_url']}#!/server/${parameters['pms_identifier']}/details?key=%2Flibrary%2Fmetadata%2F${featured['rating_key']}" title="Watch ${featured['title']} on Cameron-Media" target="_blank" rel="noreferrer" style="display: block;text-decoration: none;">
                                            <img class="camcore-featured-art" src="${(base_url_image + featured['art_hash']) if base_url_image else featured['art_url']}" width="1000" alt="${featured['title']} featured artwork" style="border: 0;display: block;height: auto;line-height: 0;max-width: 100%;width: 100%;">
                                        </a>
                                    </td>
                                </tr>
                                <tr>
                                    <td class="camcore-featured-copy" style="background: #0B1014;font-family: 'Open Sans', Helvetica, Arial, sans-serif;padding: 30px;text-align: left;vertical-align: top;">
                                        <p class="camcore-featured-kicker" style="color: __TEAL_LIGHT__;font-size: 12px;font-weight: 800;letter-spacing: 2px;margin: 0 0 9px;text-transform: uppercase;">Featured This Week &nbsp;•&nbsp; ${featured_kind}</p>
                                        <h1 class="camcore-featured-title" style="color: #FFFFFF;font-family: 'Open Sans', Helvetica, Arial, sans-serif;font-size: 34px;font-weight: 800;letter-spacing: -0.7px;line-height: 1.08;margin: 0 0 12px;">${featured['title']}</h1>
                                        <p class="camcore-featured-meta" style="color: #C0CDD6;font-size: 13px;font-weight: 700;line-height: 1.6;margin: 0 0 13px;">
                                            % if featured.get('year'):
                                            ${featured['year']}
                                            % endif
                                            % if featured.get('duration'):
                                            <% featured_duration = int(int(featured['duration']) / 60000) %>
                                            &nbsp;•&nbsp; ${featured_duration} min
                                            % endif
                                            % if featured.get('genres'):
                                            &nbsp;•&nbsp; ${' / '.join(featured['genres'][:2])}
                                            % endif
                                            % if featured.get('rating') or featured.get('audience_rating'):
                                            <% featured_score = int(float(featured.get('rating') or featured.get('audience_rating')) * 10) %>
                                            &nbsp;•&nbsp; ${featured_score}% rating
                                            % endif
                                        </p>
                                        % if featured.get('summary'):
                                        <p class="camcore-featured-summary" style="color: #D9E2E8;font-size: 15px;line-height: 1.55;margin: 0 0 20px;max-width: 620px;">${featured['summary'][:260] + (featured['summary'][260:] and '...')}</p>
                                        % endif
                                        <a class="camcore-watch-button" href="${parameters['pms_web_url']}#!/server/${parameters['pms_identifier']}/details?key=%2Flibrary%2Fmetadata%2F${featured['rating_key']}" title="Watch ${featured['title']} on Cameron-Media" target="_blank" rel="noreferrer" style="background: __TEAL__;border-radius: 8px;color: #FFFFFF;display: inline-block;font-size: 14px;font-weight: 800;padding: 12px 22px;text-decoration: none;">Watch on Cameron-Media</a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    % endif
'''.replace("__TEAL__", BRAND_TEAL).replace("__TEAL_LIGHT__", BRAND_TEAL_LIGHT)


for newsletter_name in ("recently_added.html", "recently_added.internal.html"):
    newsletter_path = Path("/app/tautulli/data/interfaces/newsletters") / newsletter_name
    if not newsletter_path.exists():
        continue

    newsletter = newsletter_path.read_text(encoding="utf-8-sig")

    if "CAMCORE STREAMING CATALOGUE" not in newsletter:
        style_marker = "\n    </style>"
        if style_marker not in newsletter:
            raise SystemExit(f"Unable to add streaming CSS to {newsletter_name}")
        newsletter = newsletter.replace(style_marker, STREAMING_CSS + style_marker, 1)

    if "camcore-featured-row" not in newsletter:
        section_marker = "                    % if recently_added.get('movie'):"
        if section_marker not in newsletter:
            section_marker = "                    % if recently_added.get('show'):"
        if section_marker not in newsletter:
            raise SystemExit(f"Unable to add featured title to {newsletter_name}")
        newsletter = newsletter.replace(section_marker, FEATURED_BLOCK + section_marker, 1)

    newsletter = newsletter.replace(
        "${message if '<' in message and '>' in message else '<br>'.join(l for l in message.splitlines()) | n}",
        "${message.replace('```', '') if '<' in message and '>' in message else '<br>'.join(l for l in message.replace('```', '').splitlines()) | n}",
    )

    newsletter = newsletter.replace(
        "${movie['summary'][:450] + (movie['summary'][450:] and '...')}",
        "${movie['summary'][:150] + (movie['summary'][150:] and '...')}",
    )
    newsletter = newsletter.replace(
        "${show['season'][0]['episode'][0]['summary'][:350] + (show['season'][0]['episode'][0]['summary'][350:] and '...')}",
        "${show['season'][0]['episode'][0]['summary'][:150] + (show['season'][0]['episode'][0]['summary'][150:] and '...')}",
    )
    newsletter = newsletter.replace(
        "<% length = max(0, 350 - 50 * (show['season_count'] - 1)) %>",
        "<% length = max(0, 150 - 25 * (show['season_count'] - 1)) %>",
    )

    newsletter = re.sub(
        r"\n\s*% if movie\['tagline'\]:\s*\n\s*<p class=\"nowrap mb5\".*?</p>\s*\n\s*% endif",
        "",
        newsletter,
        flags=re.S,
    )

    newsletter_path.write_text(newsletter, encoding="utf-8")
