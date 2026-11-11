# Bollnäs Kalender
Public 14-day events PWA for Bollnäs kommun.

## Publish
Upload the *contents* of this folder to the repository (not the ZIP file). In Settings → Pages, choose Deploy from a branch, `main`, `/ (root)`.

## Updates
Actions → Uppdatera evenemang → Run workflow to test. The scheduled job runs at 05:00 UTC (06:00 CET winter, 07:00 CEST summer). GitHub schedules may be delayed or disabled after prolonged inactivity.

## Coverage limitation
This starter collector reads structured Event JSON-LD from the municipality's events page only. Many events will not be captured, and a source may return zero events. Additional verified source adapters must be added for trav, bandy, hockey, loppisar, auctions, etc. No invented listings are shown. The event-tip link currently requires GitHub login. No guarantees of completeness.
