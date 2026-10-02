# Doors: event discovery app

A five-screen, mobile-first web app for finding events in Chicago. You can browse upcoming events, filter them by date, read the details, save events for later and buy tickets.

It is plain HTML, CSS and JavaScript with no build step and no runtime dependencies. All events, venues and people are invented sample data, and checkout is simulated.

## Run it

Open `index.html` in a browser. To serve it over HTTP instead:

```bash
cd apps/event-discovery
python3 -m http.server 4173   # then open http://localhost:4173
```

Links can go straight to a screen: `#discover`, `#search`, `#saved`, `#account`, or `#event-e04` for one event.

## Screens

| Screen | What it shows |
| --- | --- |
| **Discover** | Event counts for tonight, tomorrow, this weekend and the next 7 days; featured events; categories; "Picked for you" based on favorite categories; upcoming events grouped by day. Every card shows the name, date, venue, category and price, and opens the event. |
| **Search** | Text search over titles, venues, neighborhoods and lineups. Date presets (Today, Tomorrow, This weekend, Next 7 days, Next 30 days), a 28-day strip with a dot for each event, and a date picker for any other day. Category chips, sorting by date or price, and a result count. |
| **Event** | Poster, title, category and age limit, date, time and door time, venue with a copy-address button, description, set times, ticket types with remaining stock, accessibility and refund details, and related events. A fixed bar shows the starting price and Save. Tapping a ticket option starts checkout. |
| **Saved** | Saved events split into this week and later, with remove and undo. A Tickets view lists purchased tickets as stubs with a barcode and order number. |
| **Account** | Profile (editable), stats, preferences (favorite categories, prices with fees, 12- or 24-hour time), notification settings, payment methods (add, remove, make default), help and FAQ, contact support, privacy and data, sign out and delete account. |

Checkout opens from a ticket option on the event screen and is a two-step sheet. You choose a ticket type and quantity, then review the total (service fee is 10% plus $1.50 per paid ticket) and pick a payment method. The result is a ticket stub saved under **Saved → Tickets**. Free events skip the payment method.

## User stories

`tests/user-stories.cjs` checks each story in headless Chromium at phone size:

| ID | Story | What the test does |
| --- | --- | --- |
| u1 | Browse upcoming events | Featured and upcoming events show name, date, location and category in date order. A card opens its event, and "See all" lists every event. |
| u2 | Filter events by date | Today, Tomorrow, This weekend, Next 7 days, a day from the strip and the date picker each return only matching dates. Date, category and text filters combine. Clear all resets them. |
| u3 | View event details | The event screen shows the title, date, time, venue, description, ticket options and the Save action, with no ticket button in the bottom bar. Going back keeps the filters. |
| u4 | Save an event for later | Saving updates both save buttons and the tab badge. The event appears on Saved, survives a reload, and can be removed and restored with Undo. |
| u5 | Purchase a ticket | Two balcony tickets total $102.00. Paying creates an order that shows under Saved → Tickets and on the event page. A free event reserves without a card. |

The test also fails on any script error and on sideways scrolling at 390px.

```bash
cd apps/event-discovery
npm install    # installs Playwright
npm test
```

## How it works

- `data.js` holds the sample categories, venues and 20 events. Event dates are relative to today (`{ in: 3 }` or `{ weekday: 6 }`), so there are always events today, tomorrow and this weekend.
- `app.js` renders each screen from state, handles routing through the URL hash, and stores saved events, tickets and settings in `localStorage`. If storage is unavailable, the app still works for the current visit.
- `styles.css` defines light and dark themes as color tokens. Event posters are generated in CSS from each event's colors, pattern and one word, so there are no image files.
- Both themes, keyboard focus, reduced motion and screen-reader labels are supported. Sheets trap focus and close with Escape.
