# Project Exit Plan — Competition Lab v0.1

Forward EV research and entry tracking for UK fixed-ticket prize competitions.

## Railway
1. Create a new GitHub repo and upload these flat files/folders.
2. Create a Railway service from the repo.
3. Add Railway Postgres to the project. Railway should expose `DATABASE_URL` to the app service.
4. Add variables from `.env.example`.
5. Deploy. Visit `/health`, then `/`.
6. Add a Railway Cron service using the same repo with start command `python collector.py` and schedule `*/10 * * * *` (UTC). The collector is idempotent and only takes snapshots when each competition is due according to adaptive polling.

## v0.1 scope
- Kilted: live collector implemented from public competition pages.
- Dream Car: discovery scaffold included; marked unhealthy unless exact max-ticket count can be verified from the competition page.
- Bounty/Rev: adapter scaffolds included. No EV is emitted unless price, prize/cash-alt, sold count, max field and close time are all trustworthy.
- Fail closed: incomplete/stale data never becomes an entry recommendation.
- Manual `I ENTERED` workflow records actual stake/tickets and freezes the observed EV state.
- Settlement can be entered manually; performance compares realised returns with expected returns.

No purchases are automated.

## v0.2.7 collector runtime
The collector is a persistent Railway worker. Start command: `python collector.py`.
Set `DATABASE_URL` as a Railway reference to Postgres. Optional: `COLLECTOR_INTERVAL_SECONDS=900` (15 minutes), `LOG_LEVEL=INFO`, `COLLECTOR_RUN_ONCE=0`.
The worker now logs database health, per-operator discovery, unhealthy rows, snapshots, qualifying EV candidates, cycle totals and sleeps between cycles. One operator failure does not stop the worker.


## v0.2.7
- Fixes naive/aware datetime arithmetic in closing-field projection.
- Isolates EV-calculation failures to an individual competition row so one bad timestamp cannot abort an entire collection cycle.

## v0.2.7
- Adds a conservative bootstrap closing-field model for new competitions.
- Requires at least 3 forward observations before a >=40% EV opportunity becomes ENTRY READY.
- Fresh high-EV observations are labelled HIGH EV — WATCH instead of qualifying.
- Uses measured sales velocity after sufficient forward history, with acceleration/reserve buffers.
- Dashboard only exposes I ENTERED for ENTRY READY opportunities.
- Server-side entry route independently enforces the same fail-closed rule.

## v0.2.7
- ENTRY READY is now restricted to the final 2 hours before close by default.
- Requires at least 4 observations spanning at least 45 minutes.
- High-EV draws outside the entry window remain HIGH EV — WATCH.
- Collector logs observation count, elapsed history, time-to-close and measured velocity.
- Dashboard and POST /enter enforce the same fail-closed gates.
- Thresholds are configurable with ENTRY_WINDOW_HOURS, MIN_ENTRY_HISTORY_HOURS and MIN_ENTRY_OBSERVATIONS.

## v0.2.7 — operator expansion
Adds fail-closed public-page adapters for:
- Click Competitions
- 7days Performance
- Elite Competitions
- Just My Luck
- Hot Comps
- 365 Competitions
- Boony Competitions

Existing Kilted, Dream Car, Bounty and Rev adapters remain. This raises the configured universe to 11 operators.
Generic adapters only persist a research-valid snapshot when exact price, sold count, max field and close time are all parsed. Entry validity additionally requires a supported cash/cash-alt prize, eligible format and guaranteed-draw evidence. Instant wins/site credit/feeders remain research-only.

## v0.2.7 — operational dashboard
- Dashboard now shows only competitions closing within the next 2 hours.
- Tomorrow/later competitions are hidden from the dashboard but still collected into Postgres for research and forecasting.
- When nothing relevant is imminent, the dashboard simply says there are no important competitions right now.
- Railway opportunity logs are also quiet outside the final 2-hour window.
- `DASHBOARD_WINDOW_HOURS` can override the display window; default is 2.
- ENTRY READY remains fail-closed and limited to the final 2 hours.

## v0.2.7 — fixed four-operator scope
Active collector universe is now deliberately restricted to:
- Kilted Competitions
- Dream Car Giveaways / Dream Comps
- Bounty Competitions
- Rev Comps

The experimental wider-site adapters remain inert in the source for now and are not called by the collector.
Dashboard remains operationally narrow: only competitions closing within the next 2 hours are shown.
Background observations continue to be retained for the four active operators.

## v0.2.7 — dashboard 500 fix
Fixes the PostgreSQL interval expression used by the final-two-hour dashboard filter.
The dashboard window is now passed as integer minutes and multiplied by a PostgreSQL interval,
avoiding the float/type mismatch from v0.1.8.
No collector, EV, entry-gating or four-operator scope rules changed.

## v0.2.7 — today's opportunity board
- Dashboard now shows all remaining tracked draws that close today in Europe/London time.
- Interesting draws currently above the +40% conservative EV hurdle are labelled INTERESTING TODAY.
- Draws inside the final 2-hour entry window continue to use HIGH EV — WATCH / ENTRY READY gating.
- ENTRY READY rules are unchanged: today's visibility does not permit premature entry.
- Today's cards are ordered with current high-EV potential first, then by closing time.
- Tomorrow and later remain hidden from the operational dashboard.

## v0.2.7 — tomorrow preview
- Keeps today's operational opportunity board unchanged.
- Adds a separate Tomorrow — Potential Draws section.
- Tomorrow cards are informational only and never expose the I ENTERED action.
- Current >=40% conservative EV is labelled POTENTIAL TOMORROW; other tomorrow draws remain TRACKING.
- Tomorrow data does not relax the final-two-hour ENTRY READY gate.

## v0.2.7 — four-site ingestion
- Replaces Dream Car, Bounty and Rev stubs with live public-page adapters.
- Dream Car opens individual competition pages for exact sold/max, price and draw time.
- Bounty discovers live entry-list pages and parses price, sold/max, close and cash alternative.
- Rev discovers current prize pages and parses sold/remaining/max, per-ticket price and guaranteed auto-draw time.
- All three remain fail-closed when required fields are absent.
- Kilted close times are now explicitly attached to Europe/London timezone.
- Active collector universe remains exactly Kilted, Dream Car, Bounty and Rev.

## v0.2.7 — closing-time ordering and bankroll-aware sizing
- Today and Tomorrow sections sort by closing time ascending, then conservative EV descending for equal close times.
- Adds recommended ticket count and £ cost for draws currently above the +40% conservative EV hurdle.
- £200/month remains a ceiling, not a target.
- Validation sizing per independent draw: 5% of monthly budget at +40–59% EV; 7.5% at +60–99%; 10% at +100–149%; 12.5% at >=+150%, capped at £25/draw.
- Expensive single tickets that materially exceed their allocation band are passed.
- Tomorrow/outside-final-window recommendations are PLANNED SIZE only. BUY SIZE is reserved for the existing final 2-hour window.
- Entry eligibility and I ENTERED gating are unchanged.

## v0.2.7 — dashboard staking hotfix
- Fixes the v0.2.3 dashboard 500 regression in bankroll sizing/rendering.
- Explicitly normalizes psycopg result rows to plain dictionaries before adding stake recommendations.
- Uses safe nested dictionary access in the Jinja template.
- Closing-time/EV ordering and £200/month proportional sizing are retained unchanged.

## v0.2.7 — exact SQL 500 fix
- Fixes the dashboard traceback: base_sql contains one psycopg placeholder (day offset)
  but v0.2.3/v0.2.4 passed two parameters (day offset + threshold).
- Today now executes with (0,) and Tomorrow with (1,).
- No collector, sorting, EV, staking, or entry-gating behavior changed.

## v0.2.7 — Dream competition-specific draw date
- Fixes Dream closing-date extraction.
- The adapter now prioritises the competition-specific Details sentence:
  "The draw date for this competition is DD/MM/YYYY at HH:MMPM ..."
- Generic page labels such as "Automated Draw This Wednesday, 22:00" are only fallback data.
- Parsed Dream draw dates are explicitly Europe/London aware.
- Existing sold/max parsing, EV logic, staking and dashboard sorting are unchanged.

## v0.2.7 — Dream Details authoritative parser
- Dream closing date/time is now read ONLY from the Competition Details section sentence
  "The draw date for this competition is DD/MM/YYYY at HH:MMPM ...".
- Removed the generic Dream Automated Draw/Today/Tomorrow fallback entirely.
  If Competition Details cannot be parsed, the row fails closed and cannot appear as an actionable draw.
- Dream sold/max supports both the compact sold/max display and the explicit Details wording.
- Also fixes a separate critical Dream prize contamination visible on the dashboard:
  cash competition prize is now taken from the competition title (e.g. Win £1,000 Tax Free Cash => £1,000),
  rather than the largest unrelated £ value elsewhere on the page.
- Kilted is unchanged.

## v0.3.0 — clean cash opportunity universe
- Dream discovery starts from the dedicated /competitions/cash page.
- Dream only admits simple cash end-prize competitions; prize is parsed from that competition title only.
- Dream close date/time must come from the individual page's exact "draw date for this competition is DD/MM/YYYY at HH:MM..." wording.
- Generic Automated Draw timers are never used.
- Exact sold/max remains sourced from the individual competition page.
- Kilted obvious Golden Ticket/feeder wording is excluded from entry scope without changing its working date/sold parser.
- Negative conservative-EV competitions remain in Postgres research but are hidden from Today/Tomorrow action cards.

## v0.3.1 — Dream cash recovery
- Fixes Dream returning 0 rows.
- Root cause: Dream's Competition Details accordion is JavaScript-rendered and is absent from the HTML returned to the Railway requests collector, so v0.3.0's required explicit Details date was always null.
- For Today/Tomorrow only, close time now comes from the matching competition card on Dream's dedicated Cash page.
- Exact ticket price and exact sold/max continue to come from the individual competition page.
- Only straightforward cash competitions are admitted; instant wins/points/site-credit structures remain excluded.
- No unrelated generic page timer is used: the fallback is the competition's own Cash-listing card.

## v0.3.2 — collector diagnostics
- Dream adapter now logs every parsing stage: cash-page anchors, unique competition URLs,
  cards with close labels, pages fetched, cash-title matches, price matches, sold/max matches,
  close matches, and accepted rows.
- Up to eight safe rejection samples are logged per cycle with a reason such as NO_CARD_CLOSE,
  NO_CASH_TITLE, NO_PRICE, NO_SOLDMAX, or NO_CLOSE.
- If Dream's card nesting has changed and zero close-labelled cards are found, the adapter
  inspects the unique competition links rather than silently returning zero.
- This release is intentionally diagnostic: it does not relax the +40% entry threshold or
  change Kilted's working sold/date parser.
