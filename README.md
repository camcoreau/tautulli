# CamCore Media Insights

CamCore-maintained downstream of [Tautulli](https://github.com/Tautulli/Tautulli) for monitoring, analytics, notifications and weekly Cameron-Media updates.

The CamCore image keeps Tautulli's upstream functionality while applying CamCore visual identity, notification wording, sender standards, newsletter presentation and a controlled GHCR release workflow.

## CamCore service identity

| Surface | CamCore identity |
| --- | --- |
| Application | `CamCore Media Insights` |
| Purpose | Monitoring and analytics for Cameron-Media |
| Container | `ghcr.io/camcoreau/tautulli` |
| Operational email sender | `Insights | CamCore Media <help@camcore.au>` |
| Newsletter sender | `Updates | CamCore Media <help@camcore.au>` |
| Cameron-Media | `https://plex.camcore.au` |
| Requests | `https://requests.camcore.au` |
| Service status | `https://status.camcore.au` |
| Support | `https://camcore.au/support.html` |

## CamCore customisation

The downstream layer includes:

- CamCore Media Insights browser, navigation, login and favicon branding;
- CamCore-branded newsletter authentication pages;
- Cameron-Media weekly update/newsletter presentation;
- a featured weekly media catalogue and responsive Outlook-friendly layout;
- CamCore operational email subjects and content;
- embedded CamCore artwork in operational email notifications;
- CamCore sender identities for alerts and newsletters;
- transparent migration of untouched upstream Tautulli notification defaults;
- a validation-gated GHCR build for the CamCore image.

CamCore-specific modifications are applied at image build time on top of the LinuxServer Tautulli image. This keeps the maintained downstream small and reduces conflicts when Tautulli changes upstream.

## Email communication standard

### Operational notifications

Operational notifications use:

```text
Insights | CamCore Media <help@camcore.au>
```

Stock Tautulli subjects such as `Tautulli ({server_name})` are replaced with event-first subjects, for example:

```text
Playback started — <title>
Buffering detected — <title>
New playback device — <user>
Cameron-Media is unavailable
Cameron-Media is back online
Cameron-Media remote access restored
Plex Media Server update available
Media Insights update available
Media Insights database issue detected
Media Insights lost Plex access
```

Operational HTML email uses the same CamCore communication system as other CamCore services: dark CamCore header, cyan divider, event badge, white content panel, service details, primary action and CamCore support/status links.

Existing notifier subjects and bodies are only automatically upgraded when they still match the untouched upstream Tautulli defaults. Deliberately customised notification text is preserved.

### Cameron-Media weekly updates

Weekly updates use:

```text
Updates | CamCore Media <help@camcore.au>
```

The default subject is:

```text
What's new on Cameron-Media — <date>
```

The newsletter includes direct pathways to Cameron-Media, Cameron-Media Requests, Service Status and CamCore Support.

## Container image

Successful production builds publish:

```text
ghcr.io/camcoreau/tautulli:latest
ghcr.io/camcoreau/tautulli:camcore
ghcr.io/camcoreau/tautulli:master-<sha>
```

The CamCore deployment image is built for:

```text
linux/amd64
```

Change branches run validation without publishing. `master` publishes only after the CamCore patch layer has been applied and the patched Tautulli Python modules compile successfully.

## Existing configuration

Tautulli configuration and its database remain outside the container image in the normal LinuxServer `/config` volume. Keep the existing `/config` mapping when updating the CamCore image.

Before an update:

1. back up the existing Tautulli `/config` directory;
2. record the currently deployed image tag or digest;
3. confirm the CamCore workflow completed successfully;
4. pull the required CamCore image;
5. recreate the container without changing the `/config` mapping;
6. verify Tautulli, Plex connectivity, notifications and newsletters.

## Keeping the downstream current

The fork should remain close to `Tautulli/Tautulli:master`.

When incorporating upstream changes:

1. sync upstream Tautulli into this repository;
2. run the CamCore validation workflow;
3. confirm all patch scripts still apply cleanly;
4. review Tautulli notification/newsletter changes that may affect the downstream layer;
5. publish the validated CamCore image;
6. deploy while preserving `/config`;
7. verify Media Insights and email/newsletter delivery.

## Upstream project

The underlying application is developed by the [Tautulli project](https://github.com/Tautulli/Tautulli) and its open-source contributors.

For upstream Tautulli documentation, releases and general application issues, use the upstream project resources:

- [Tautulli repository](https://github.com/Tautulli/Tautulli)
- [Tautulli releases](https://github.com/Tautulli/Tautulli/releases)
- [Tautulli wiki](https://github.com/Tautulli/Tautulli/wiki)
- [Tautulli issue tracker](https://github.com/Tautulli/Tautulli/issues)

CamCore-specific deployment, branding and operational matters should use CamCore Support.

## Licence

This downstream remains subject to the upstream [GNU General Public License v3.0](LICENSE).
