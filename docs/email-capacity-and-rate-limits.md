# Email capacity and rate limits

## Application-level budget

`DAILY_SEND_LIMIT` configures the maximum number of send attempts counted by the application over a rolling 24-hour window. The default and `.env.example` value are 50. The sender counts messages that are `sent`, `sending` or `unknown`, so ambiguous outcomes and in-flight attempts continue consuming budget and cannot be blindly retried.

`GET /mailbox/capacity` reports the configured application limit, counted attempts, remaining application budget, whether sending is enabled, unsubscribe-footer status, and requested/configured public tracking status with a limitation note. The follow-up and embedded Lead 360 screens display this status. It is an operational indicator, not a send guarantee: campaign approval, mailbox synchronization, suppression and other gates still apply.

Set the limit only after confirming the approved Gmail account's policy and intended send volume. Do not copy a provider's maximum as a target. Gmail may impose lower limits or additional restrictions. This application cap is not account-aware and cannot detect Gmail's current quota state.

## Safety and limitations

- Sending remains disabled by default (`MAIL_SEND_ENABLED=false`).
- `MAIL_UNSUBSCRIBE_ENABLED=true` is the default and requires an approved HTTPS base for unsubscribe links. Explicit `false` removes only the footer/headers and that prerequisite. It does not bypass inbox monitoring, opt-out reply processing, suppressions, approvals, uncertain-send reconciliation or the budget.
- `TRACKING_ENABLED=true` requires an approved reachable HTTPS endpoint for real open/click signals. Without an HTTPS base and with unsubscribe links disabled, the sender logs a warning and sends without pixels or redirects; the UI reports that limitation. SMTP acceptance and matched replies remain recorded. Configuring a URL does not verify its reachability.
- No per-minute pacing, provider feedback integration or user-configurable UI control is implemented; the limit is configured through the server environment.
- SMTP ambiguity remains a manual-reconciliation case. `unknown` is counted to prevent automatic repeat attempts.
- The application budget is shared across campaigns on this configured service account.
- The local unauthenticated pilot is not production-ready. Explicitly enabling sending can release approved due messages in active campaigns; do not enable it based on this display alone or publish the app. Follow applicable organizational, provider and consent requirements.
