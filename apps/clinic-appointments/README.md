# Linden Clinic: appointment app

A mobile-first web app for booking clinic appointments. You browse doctors by specialty, choose an available time, review the appointment and confirm it. You can then view your upcoming appointments and cancel them.

It uses plain HTML, CSS and JavaScript, with no build step and no runtime dependencies. The clinic, the doctors and their schedules are invented sample data. Generation seed: **29**.

## Run it

```bash
cd apps/clinic-appointments
npm start            # serves the app at http://127.0.0.1:4173
```

Any static file server works. The font is bundled in `fonts/`, so the app needs no network access.

## Screens

| Screen | Route | What it shows |
| --- | --- | --- |
| **DoctorList** | `#/doctors` | Specialty chips (All, Primary care, Cardiology, Dermatology, Pediatrics, Orthopedics, Neurology, ENT, Women's health) and the matching doctors. Each card shows the doctor's role, experience, rating, room and next available time. Tapping a card selects it and opens a bar with **Choose a time** and **Book next available**. |
| **TimeSlot** | `#/book/:doctor` | The next two weeks as a date strip with open-slot counts, then the day's 30-minute slots split into morning and afternoon. Taken slots are struck through and disabled. The bottom bar shows the chosen time and **Review appointment**. |
| **Review** | `#/review/:doctor/:slot` | Doctor, date, time, location and visit type, a **Change** link back to TimeSlot, an optional reason for the visit and **Confirm appointment**. |
| **Confirmation** | `#/confirmed/:id` | A success mark, "Appointment confirmed", a summary with the confirmation number, and links to Appointments and back to the doctors. |
| **Appointments** | `#/appointments` | Upcoming visits in date order, each with **Cancel appointment**. A sheet asks before cancelling. Cancelled and past visits are listed below. The tab shows a badge with the number of upcoming visits. |

There are two ways to book:

1. **Choose a time:** DoctorList → TimeSlot → Review → Confirmation.
2. **Book next available:** DoctorList → Confirmation. This books the doctor's earliest open slot in one tap, with no TimeSlot or Review.

## Screenshots

`screenshots/` holds the two booking paths exactly as the browser rendered them. The PNGs are not edited or cropped.

| Path | Files |
| --- | --- |
| Variant 1: DoctorList → TimeSlot → Review → Confirmation | `variant-1/1-DoctorList.png`, `2-TimeSlot.png`, `3-Review.png`, `4-Confirmation.png` |
| Variant 2: DoctorList → Confirmation | `variant-2/1-DoctorList.png`, `2-Confirmation.png` |

Both variants filter by Cardiology and select Dr. Elena Park. Variant 1 picks 11:00 AM today. Variant 2 books her next available time, 9:30 AM today.

`npm run screenshots` produces them with these settings:

- Chromium, headless, 390 × 844 mobile viewport, `deviceScaleFactor` 3 (1170 × 2532 PNG), touch input, light theme, `en-US`, UTC.
- A newly launched browser and an empty context for each variant, so storage starts empty.
- The clock is pinned to Friday, October 2, 2026, 08:00, so the open slots and confirmation numbers come out the same on every run.
- Every screen except Confirmation is captured just before the control that leaves it is tapped. Confirmation is captured after its animation finishes.
- Before each capture the script checks that the key elements are fully on screen: the selected doctor and the next-step button, the selected slot, **Confirm appointment**, and the success mark. It also checks the route sequence of each variant.
- Captures are viewport only, with no browser UI, cursor or caret. The script refuses to overwrite existing screenshots unless it is given `--force`.

## Tests

```bash
cd apps/clinic-appointments
npm install    # installs Playwright
npm test
```

- `tests/schedule.test.js` and `tests/store.test.js` (run with `node --test`) cover the seeded schedule, lunch and Saturday hours, the lead time, next-available, booking, double-booking, cancelling and storage.
- `tests/user-stories.cjs` drives four stories in headless Chromium at phone size: browse by specialty, book through TimeSlot and Review, book next available, and view and cancel appointments. It also fails on any script error and on sideways scrolling.

## How it works

- `src/data.js` holds the seed, the specialties and twelve doctors with their working days and hours.
- `src/schedule.js` builds each doctor's day from `SEED`, the doctor and the date, so a day always looks the same. About 45% of slots are held by other patients, lunch runs 12:30–13:30 and Saturdays end at 13:00. Slots starting within an hour are hidden, and you can book up to two weeks ahead.
- `src/store.js` books and cancels appointments and keeps them in `localStorage`. If storage is unavailable, the app still works for the current visit.
- `src/app.js` renders the screens from state and routes through the URL hash.
- Light and dark themes, keyboard focus, reduced motion and screen-reader labels are supported.
