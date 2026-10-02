# Workset

A five-screen fitness tracker that runs in the browser. It shows today's workout,
lets you browse routines and exercises, log a completed session set by set,
review the week's training, and manage goals and preferences.

It is plain HTML, CSS and JavaScript modules with no build step and no
dependencies. Data stays in the browser's `localStorage`.

## Run it

ES modules don't load from `file://`, so serve the folder over HTTP:

```bash
cd apps/fitness-tracker
python3 -m http.server 8080      # or: npm start
```

Then open <http://localhost:8080>.

## Test it

```bash
cd apps/fitness-tracker
npm test                         # node --test, Node 20 or newer, nothing to install
```

The tests cover the pure logic: dates and weeks, weekly statistics, streaks,
one-rep-max trends, the logging draft and its validation, persistence, the
weekly plan, unit conversion, routing and HTML escaping.

## Screens

| Route | Screen | What it does |
| --- | --- | --- |
| `#today` | Dashboard | Today's assigned workout with its duration, exercises and prescription, an **Open workout** action, and a summary of the current week: a day-by-day strip, workouts and minutes against your weekly targets, and volume compared with last week. Shows a rest-day view when nothing is planned. |
| `#workouts` | Workouts | Routine library filtered by category, level and search. Each card shows duration, difficulty and focus. The Exercises tab lists the catalog by muscle group. `#workout-<id>` opens a routine with **Log this workout** and **Do it today instead**. |
| `#log` | Log | Record a session: start from a routine or from scratch, set date, duration and effort (RPE), and edit exercises, sets, weight and reps. Each exercise shows what you did last time. **Save session** validates the entry and saves it. |
| `#progress` | Progress | Weekly totals for workouts, active time, volume and average effort. Charts show minutes by day, consistency over eight weeks against your goal (with streak), sets by muscle group and the estimated 1RM trend for a lift. You can step back through earlier weeks and delete sessions. |
| `#profile` | Profile | Weekly targets and personal goals (add, update, remove; goals can count down, such as a run time), experience level, preferred session length, the weekly plan, notification preferences, units, first day of the week, appearance and data reset. |

On a phone the screens sit behind a bottom tab bar. From 960px wide they use a
side rail and two-column layouts. Light and dark themes follow the system, or
you can choose one in Profile.

## Sample data

On first run the app seeds a weekly plan, goals and eight weeks of sample
sessions dated relative to today, so the charts have something to show. Sample
sessions are tagged in the UI. **Profile → Your data → Clear samples** removes
them and keeps anything you logged.

## Notes

- Weights are stored in kilograms and converted for display when you choose pounds.
- Volume is weight × reps over rep-based sets. Timed sets (planks, runs) count toward sets and minutes, not volume.
- Estimated 1RM uses the Epley formula on each week's best set of 12 reps or fewer.
- Reminders, weekly summaries, milestones and rest-day check-ins appear inside the app while it is open. It does not send push notifications.

## Layout

```
index.html          app shell
styles.css          design tokens (light and dark) and all styles
src/
  main.js           routing, rendering, event delegation, toasts
  routes.js         hash routes
  store.js          state, persistence and pure state updates
  seed.js           first-run plan, goals and sample sessions
  catalog.js        exercises and workout routines
  plan.js           weekly plan and day status
  draft.js          the session being logged and its validation
  stats.js          weekly statistics, streaks, 1RM trends
  dates.js, units.js, html.js, charts.js, components.js
  screens/          dashboard, workouts, log, progress, profile
tests/              node:test suites
```
