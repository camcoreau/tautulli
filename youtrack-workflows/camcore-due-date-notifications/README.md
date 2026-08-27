# CamCore due date notifications

This workflow is the source-controlled CamCore replacement for the stock YouTrack
`Notify assignee about overdue issues` rule from
`@jetbrains/youtrack-workflow-due-date`.

It keeps the stock overdue behaviour and changes the email presentation only:

- unresolved issues with a `Due Date` are checked at 10:00 Monday to Friday;
- a task is overdue when its due date is earlier than the current time;
- the assignee is notified when one is present;
- otherwise, the project leader is notified;
- the subject is `Action required | CamCore task overdue`;
- the body uses the CamCore Operations email system: dark header, cyan divider,
  action badge, task details, due date, primary CamCore Tasks action and CamCore
  support/status links;
- issue-controlled text is HTML-escaped before it is inserted into the message;
- the default `[YouTrack, Issue is overdue]` subject and `Sincerely yours, YouTrack`
  footer are not used.

The workflow intentionally leaves the sender identity to the existing YouTrack
mail/project configuration. On CamCore this should remain the configured
`YouTrack | CamCore Operations <help@camcore.au>` sender.

## Build the upload package

Create the ZIP with only the workflow files. Do not include the `tests` directory
in the YouTrack upload package.

```bash
cd youtrack-workflows/camcore-due-date-notifications
zip -j camcore-due-date-notifications.zip manifest.json overdue-notifications.js
```

## Deploy to YouTrack

1. In YouTrack, open **Administration > Workflows**.
2. Select **New workflow > Upload ZIP file...** and upload
   `camcore-due-date-notifications.zip`.
3. Attach **CamCore Due Date Notifications** to every CamCore project where the
   stock overdue notification rule is currently active.
4. In each of those projects, open the stock **Due Date** workflow and deactivate
   **Notify assignee about overdue issues**.
5. Keep **Require due dates for submitted issues** active if the project still
   requires that stock validation rule.
6. Confirm the CamCore rule is active and that the project has both `Due Date`
   and `Assignee` fields available to the workflow.
7. Test with a non-production task that has an expired due date, then confirm the
   message arrives from the existing CamCore Operations sender with the branded
   subject and HTML body.

The stock overdue rule must be disabled wherever the CamCore rule is enabled.
Running both rules on the same project will send duplicate overdue emails.

## Maintenance

The stock behaviour mirrored here is based on YouTrack Server 2026.2. When
YouTrack is upgraded, compare this rule with JetBrains' current Due Date workflow
before changing the scheduling or recipient-selection logic.

JetBrains references:

- https://www.jetbrains.com/help/youtrack/devportal/Workflow-Due-Date.html
- https://www.jetbrains.com/help/youtrack/server/import-export-workflows.html
- https://www.jetbrains.com/help/youtrack/server/manage-workflows.html
