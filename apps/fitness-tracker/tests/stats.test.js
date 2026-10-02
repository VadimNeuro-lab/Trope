import test from 'node:test';
import assert from 'node:assert/strict';
import {
  consistencyRate,
  estimateOneRepMax,
  goalProgress,
  goalStreak,
  lastPerformance,
  liftTrend,
  liftsWithHistory,
  muscleBreakdown,
  percentChange,
  sessionVolume,
  summarizeWeek,
  weeklyHistory,
} from '../src/stats.js';

const TODAY = new Date(2026, 9, 2); // Friday

const session = (date, overrides = {}) => ({
  id: date,
  date,
  name: 'Session',
  minutes: 50,
  rpe: 8,
  loggedAt: `${date}T18:00:00.000Z`,
  exercises: [
    {
      exerciseId: 'bench-press',
      group: 'chest',
      measure: 'reps',
      sets: [
        { reps: 5, weight: 100 },
        { reps: 5, weight: 100 },
      ],
    },
    { exerciseId: 'plank', group: 'core', measure: 'time', sets: [{ reps: 60, weight: 0 }] },
  ],
  ...overrides,
});

test('volume counts weight × reps and ignores timed sets', () => {
  assert.equal(sessionVolume(session('2026-10-01')), 1000);
});

test('weekly summary groups sessions into the right days', () => {
  const sessions = [
    session('2026-09-27'), // Sunday of the previous Monday-week
    session('2026-09-28', { minutes: 40, rpe: 6 }),
    session('2026-10-01'),
    session('2026-10-01', { id: 'b', minutes: 20, rpe: 7 }),
  ];
  const week = summarizeWeek(sessions, TODAY, 1);
  assert.equal(week.count, 3);
  assert.equal(week.minutes, 110);
  assert.equal(week.volume, 3000);
  assert.equal(week.activeDays, 2);
  assert.equal(week.avgRpe, 7);
  assert.equal(week.days[3].sessions.length, 2);
  assert.equal(week.days[3].minutes, 70);

  const sundayWeek = summarizeWeek(sessions, TODAY, 0);
  assert.equal(sundayWeek.count, 4);
});

test('an empty week has no average effort', () => {
  assert.equal(summarizeWeek([], TODAY, 1).avgRpe, null);
});

test('history, streaks and consistency', () => {
  const sessions = ['2026-09-14', '2026-09-15', '2026-09-21', '2026-09-22', '2026-09-28'].map((d) => session(d));
  const history = weeklyHistory(sessions, TODAY, 1, 4);
  assert.deepEqual(
    history.map((w) => w.count),
    [0, 2, 2, 1],
  );
  // The current week is unfinished, so missing the target there keeps the streak alive.
  assert.equal(goalStreak(history, 2), 2);
  assert.equal(goalStreak([...history.slice(0, 3), { count: 3 }], 2), 3);
  assert.equal(goalStreak(history, 3), 0);
  assert.equal(consistencyRate(history, 2), 2 / 3);
});

test('muscle breakdown counts sets per group', () => {
  assert.deepEqual(muscleBreakdown([session('2026-10-01'), session('2026-10-02')]), [
    { group: 'chest', sets: 4 },
    { group: 'core', sets: 2 },
  ]);
});

test('one-rep max estimates', () => {
  assert.equal(estimateOneRepMax(100, 1), 100);
  assert.equal(Math.round(estimateOneRepMax(100, 5) * 10) / 10, 116.7);
  assert.equal(estimateOneRepMax(100, 15), null);
  assert.equal(estimateOneRepMax(0, 5), null);
});

test('lift trend keeps the best set per week and leaves gaps empty', () => {
  const heavy = session('2026-09-29', {
    exercises: [{ exerciseId: 'bench-press', group: 'chest', measure: 'reps', sets: [{ reps: 3, weight: 110 }] }],
  });
  const trend = liftTrend([session('2026-09-15'), session('2026-10-01'), heavy], 'bench-press', TODAY, 1, 3);
  assert.deepEqual(
    trend.map((p) => p.value),
    [116.7, null, 121],
  );
  assert.deepEqual(liftsWithHistory([session('2026-09-15')]), ['bench-press']);
});

test('last performance looks only at earlier days, whatever the order', () => {
  const older = session('2026-09-20', { exercises: [{ exerciseId: 'bench-press', measure: 'reps', sets: [{ reps: 8, weight: 80 }] }] });
  const newer = session('2026-09-27');
  const same = session('2026-10-02');
  const last = lastPerformance([newer, same, older], 'bench-press', '2026-10-02');
  assert.equal(last.date, '2026-09-27');
  assert.equal(lastPerformance([newer], 'deadlift', '2026-10-02'), null);
});

test('relative change and goal progress', () => {
  assert.equal(percentChange(120, 100), 0.2);
  assert.equal(percentChange(10, 0), null);
  assert.equal(goalProgress({ start: 85, current: 95, target: 110 }), 0.4);
  // A goal that counts down, like a run time.
  assert.equal(goalProgress({ start: 31, current: 28, target: 25 }), 0.5);
  assert.equal(goalProgress({ start: 4, current: 14, target: 12 }), 1);
  assert.equal(goalProgress({ start: 4, current: 2, target: 12 }), 0);
});
