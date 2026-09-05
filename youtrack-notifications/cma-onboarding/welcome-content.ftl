                            <div style="display:inline-block;margin:0 0 18px;padding:7px 11px;border:1px solid #FF4B2B;border-radius:20px;background-color:#F4F6F8;color:#C8321A;font-size:11px;line-height:14px;font-weight:bold;letter-spacing:1.2px;text-transform:uppercase;">
                                Your access is ready
                            </div>
                            <h1 style="margin:0 0 16px;color:#101720;font-size:28px;line-height:35px;font-weight:700;">
                                Welcome to Cameron-Media
                            </h1>
                            <p style="margin:0 0 18px;color:#667180;font-size:16px;line-height:25px;">
                                Welcome to <strong style="color:#101720;">Cameron-Media</strong>, the media streaming service provided as part of <strong style="color:#101720;">CamCore</strong>.
                            </p>
                            <p style="margin:0 0 26px;color:#667180;font-size:16px;line-height:25px;">
                                Your access is now ready. Sign in using the same Plex account that received your library invitation.
                            </p>
                            <h2 style="margin:0 0 14px;color:#101720;font-size:20px;line-height:27px;">Get started</h2>
                            <ol style="margin:0 0 26px;padding-left:24px;color:#667180;font-size:15px;line-height:24px;">
                                <li style="margin-bottom:14px;"><strong style="color:#101720;">Accept your Plex invitation</strong><br>If you have not already, accept the Cameron-Media library invitation sent by Plex.</li>
                                <li style="margin-bottom:14px;"><strong style="color:#101720;">Open Cameron-Media</strong><br>Open the <a href="https://app.plex.tv/desktop/" style="color:#C8321A;">Plex Web App</a> or install Plex for your TV, phone, tablet or computer from <a href="https://www.plex.tv/apps-devices/" style="color:#C8321A;">Plex Apps &amp; Devices</a>.</li>
                                <li><strong style="color:#101720;">Find your libraries</strong><br>Select <strong>Cameron-Media</strong> in Plex and pin the libraries you use most so they stay easy to find.</li>
                            </ol>
                            <h2 style="margin:0 0 14px;color:#101720;font-size:20px;line-height:27px;">Your CamCore services</h2>
                            <p style="margin:0 0 14px;color:#667180;font-size:15px;line-height:24px;"><strong style="color:#101720;">Cameron-Media</strong><br>Your Plex-based media service for movies, TV shows and other shared content.</p>
                            <p style="margin:0 0 14px;color:#667180;font-size:15px;line-height:24px;"><a href="https://camcore.au" style="color:#C8321A;font-weight:bold;">CamCore</a><br>The main website for CamCore and its services.</p>
                            <p style="margin:0 0 14px;color:#667180;font-size:15px;line-height:24px;"><a href="https://requests.camcore.au" style="color:#C8321A;font-weight:bold;">Media Requests</a><br>Request movies and TV shows you would like added to Cameron-Media.</p>
                            <p style="margin:0 0 26px;color:#667180;font-size:15px;line-height:24px;"><a href="https://status.camcore.au" style="color:#C8321A;font-weight:bold;">Service Status</a><br>Check service availability, planned maintenance and known outages.</p>
                            <h2 style="margin:0 0 14px;color:#101720;font-size:20px;line-height:27px;">Need help?</h2>
                            <#if commentFromReply>
                            <p style="margin:0 0 14px;color:#667180;font-size:15px;line-height:24px;">Reply directly to this email, open your welcome ticket below, or email <a href="mailto:help@camcore.au" style="color:#C8321A;">help@camcore.au</a>.</p>
                            <#else>
                            <p style="margin:0 0 14px;color:#667180;font-size:15px;line-height:24px;">Reply through your welcome ticket below or email <a href="mailto:help@camcore.au" style="color:#C8321A;">help@camcore.au</a>.</p>
                            </#if>
                            <p style="margin:0 0 22px;color:#667180;font-size:14px;line-height:22px;">Include your device, what you were trying to do, any error message and a screenshot where possible.</p>
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 18px;"><tr><td bgcolor="#C8321A" style="border-radius:8px;text-align:center;"><a href="${confirmationURL}" style="display:inline-block;padding:14px 24px;color:#FFFFFF;font-size:15px;line-height:19px;font-weight:bold;text-decoration:none;border-radius:8px;">Open your welcome ticket</a></td></tr></table>
                            <p style="margin:0 0 26px;color:#667180;font-size:13px;line-height:21px;">Your reference: <strong style="color:#101720;">${issue.id}</strong>. Keep this email if you need help later. No reply is needed to complete your welcome.</p>
                            <p style="margin:0 0 28px;color:#667180;font-size:15px;line-height:24px;">Enjoy Cameron-Media!</p>
