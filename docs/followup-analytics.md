# Follow-up analytics

## Campaign summary

`GET /campaigns/{campaign_id}/analytics` provides counts for enrolled, active, stopped, suppressed, replied, and accepted recipients, as well as messages with a recorded send acceptance. It also reports unique recipients with an open or click event and rates for replies, opens and clicks.

The denominator for engagement rates is unique enrollments with at least one recorded acceptance, not total messages or number of events. Each enrollment has a unique address within a campaign, so recipients are not double-counted when they receive multiple sequence messages. An open/click is counted at most once per enrollment regardless of repeated events.

The follow-up screen shows this summary for the selected campaign. A zero denominator results in a null rate, displayed as unavailable rather than 0%.

## Interpretation and limitations

- “Recorded acceptance” means SMTP accepted the message or sales manually reconciled it as accepted. It is not a delivery receipt.
- An incoming matched reply is counted at the enrollment level.
- Open and click signals are approximate. Email-client proxies, security scanners, image blocking, caching and automatic link checks can affect them; they are not proof of human engagement.
- This first version has no date-range filtering, CSV export, cross-campaign roll-up or activity cohort breakdown.
- Suppression counts include every suppression reason, not only unsubscribes.
- Unmatched inbox replies are not assigned to a campaign and are excluded from campaign reply metrics.

The API is local-only and unauthenticated along with the rest of the pilot. Do not expose recipient or campaign analytics publicly.
