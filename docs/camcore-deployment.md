# CamCore Media Insights Deployment

The CamCore-maintained Tautulli image is published to:

```text
ghcr.io/camcoreau/tautulli:latest
```

The production image is built for `linux/amd64`.

## Persistent data

Keep the existing LinuxServer Tautulli `/config` volume unchanged when updating the image. The CamCore branding, email renderer and notification defaults are part of the container image; Tautulli settings, database, history and notifier configuration remain in `/config`.

Before updating:

1. back up the Tautulli `/config` directory;
2. record the current image tag or digest;
3. confirm the CamCore image workflow completed successfully;
4. pull the new image;
5. recreate the container with the same `/config`, ports, network and environment settings.

## CamCore email identity

### Operational notifications

Expected sender:

```text
Insights | CamCore Media <help@camcore.au>
```

CamCore automatically replaces the untouched upstream sender name `Tautulli` with `Insights | CamCore Media` when sending. The configured sender email address remains under Tautulli administrator control and should be set to `help@camcore.au` for the full CamCore standard.

Operational email uses a CamCore HTML wrapper with an embedded logo so Outlook does not depend on external-image loading.

Stock upstream Tautulli notification text is transparently upgraded at runtime for Email notifiers only. If a subject or body has been deliberately customised, CamCore leaves it unchanged.

### Weekly Cameron-Media updates

Expected sender:

```text
Updates | CamCore Media <help@camcore.au>
```

Default subject:

```text
What's new on Cameron-Media — <date>
```

Existing newsletters that still use `Tautulli Newsletter` or `Recently Added to {server_name}! ({end_date})` are upgraded in memory when generated. Custom subjects remain unchanged.

## Post-deployment verification

After pulling the updated image, verify:

- CamCore Media Insights opens normally;
- the CamCore login and navigation branding remain intact;
- Plex connectivity is healthy;
- historical Tautulli data remains available;
- an Email notifier test arrives with the embedded CamCore logo;
- the operational sender displays as `Insights | CamCore Media`;
- the test subject does not use the stock `Tautulli ({server_name})` format;
- a weekly newsletter test uses `Updates | CamCore Media` and the Cameron-Media weekly-update presentation;
- existing deliberately customised notifier subjects/bodies remain unchanged.

## Published tags

Production builds publish:

```text
ghcr.io/camcoreau/tautulli:latest
ghcr.io/camcoreau/tautulli:camcore
ghcr.io/camcoreau/tautulli:master-<sha>
```

Prefer the immutable `master-<sha>` tag when testing a new build or performing a rollback.

## Rollback

To roll back:

1. stop the current container;
2. restore the previous known-good image tag or digest;
3. keep the same `/config` volume;
4. recreate the container;
5. verify Media Insights and Tautulli notifications.

Because the CamCore changes are applied to application code inside the image rather than migrating the Tautulli database, an image rollback does not require undoing a CamCore database migration.
