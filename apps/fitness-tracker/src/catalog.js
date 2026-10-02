// Static training content: the exercise catalog and the workout library.
// Weights are stored in kilograms; time-measured exercises store seconds in `reps`.

export const MUSCLE_GROUPS = [
  { id: 'chest', label: 'Chest' },
  { id: 'back', label: 'Back' },
  { id: 'shoulders', label: 'Shoulders' },
  { id: 'arms', label: 'Arms' },
  { id: 'legs', label: 'Legs & glutes' },
  { id: 'core', label: 'Core' },
  { id: 'cardio', label: 'Cardio' },
  { id: 'mobility', label: 'Mobility' },
];

export const CATEGORIES = [
  { id: 'upper', label: 'Upper body' },
  { id: 'lower', label: 'Lower body' },
  { id: 'full', label: 'Full body' },
  { id: 'core', label: 'Core' },
  { id: 'conditioning', label: 'Conditioning' },
  { id: 'mobility', label: 'Mobility' },
];

export const LEVELS = [
  { id: 'beginner', label: 'Beginner', rank: 1 },
  { id: 'intermediate', label: 'Intermediate', rank: 2 },
  { id: 'advanced', label: 'Advanced', rank: 3 },
];

const ex = (id, name, group, equipment, measure = 'reps') => ({ id, name, group, equipment, measure });

export const EXERCISES = [
  ex('bench-press', 'Bench press', 'chest', 'Barbell'),
  ex('incline-db-press', 'Incline dumbbell press', 'chest', 'Dumbbells'),
  ex('push-up', 'Push-up', 'chest', 'Bodyweight'),
  ex('cable-fly', 'Cable fly', 'chest', 'Cable'),

  ex('pull-up', 'Pull-up', 'back', 'Bodyweight'),
  ex('barbell-row', 'Barbell row', 'back', 'Barbell'),
  ex('seated-cable-row', 'Seated cable row', 'back', 'Cable'),
  ex('db-row', 'One-arm dumbbell row', 'back', 'Dumbbells'),
  ex('lat-pulldown', 'Lat pulldown', 'back', 'Cable'),

  ex('overhead-press', 'Overhead press', 'shoulders', 'Barbell'),
  ex('lateral-raise', 'Lateral raise', 'shoulders', 'Dumbbells'),
  ex('face-pull', 'Face pull', 'shoulders', 'Cable'),
  ex('kb-clean-press', 'Kettlebell clean & press', 'shoulders', 'Kettlebell'),

  ex('triceps-pushdown', 'Triceps pushdown', 'arms', 'Cable'),
  ex('hammer-curl', 'Hammer curl', 'arms', 'Dumbbells'),
  ex('barbell-curl', 'Barbell curl', 'arms', 'Barbell'),

  ex('back-squat', 'Back squat', 'legs', 'Barbell'),
  ex('romanian-deadlift', 'Romanian deadlift', 'legs', 'Barbell'),
  ex('deadlift', 'Deadlift', 'legs', 'Barbell'),
  ex('split-squat', 'Bulgarian split squat', 'legs', 'Dumbbells'),
  ex('goblet-squat', 'Goblet squat', 'legs', 'Kettlebell'),
  ex('leg-press', 'Leg press', 'legs', 'Machine'),
  ex('walking-lunge', 'Walking lunge', 'legs', 'Dumbbells'),
  ex('leg-curl', 'Leg curl', 'legs', 'Machine'),
  ex('leg-extension', 'Leg extension', 'legs', 'Machine'),
  ex('calf-raise', 'Standing calf raise', 'legs', 'Machine'),
  ex('glute-bridge', 'Glute bridge', 'legs', 'Bodyweight'),
  ex('kb-swing', 'Kettlebell swing', 'legs', 'Kettlebell'),

  ex('plank', 'Plank', 'core', 'Bodyweight', 'time'),
  ex('side-plank', 'Side plank', 'core', 'Bodyweight', 'time'),
  ex('dead-bug', 'Dead bug', 'core', 'Bodyweight'),
  ex('pallof-press', 'Pallof press', 'core', 'Cable'),
  ex('hollow-hold', 'Hollow hold', 'core', 'Bodyweight', 'time'),
  ex('farmer-carry', "Farmer's carry", 'core', 'Kettlebell', 'time'),

  ex('easy-run', 'Easy run', 'cardio', 'None', 'time'),
  ex('bike-sprint', 'Air bike sprint', 'cardio', 'Air bike', 'time'),
  ex('burpee', 'Burpee', 'cardio', 'Bodyweight'),
  ex('mountain-climber', 'Mountain climber', 'cardio', 'Bodyweight', 'time'),
  ex('rowing', 'Rowing machine', 'cardio', 'Rower', 'time'),

  ex('worlds-greatest', "World's greatest stretch", 'mobility', 'Bodyweight'),
  ex('hip-90-90', '90/90 hip switch', 'mobility', 'Bodyweight'),
  ex('cat-cow', 'Cat–cow', 'mobility', 'Bodyweight'),
  ex('thoracic-rotation', 'Thoracic rotation', 'mobility', 'Bodyweight'),
  ex('couch-stretch', 'Couch stretch', 'mobility', 'Bodyweight', 'time'),
];

const item = (exercise, sets, reps, weight = 0, rest = 90) => ({ exercise, sets, reps, weight, rest });

export const WORKOUTS = [
  {
    id: 'upper-push',
    name: 'Upper Body Push',
    short: 'Push',
    category: 'upper',
    focus: 'Strength',
    level: 'intermediate',
    minutes: 50,
    summary: 'Heavy pressing first, then shoulder and triceps volume. Rest fully between bench sets.',
    exercises: [
      item('bench-press', 4, 6, 60, 150),
      item('overhead-press', 3, 8, 35, 120),
      item('incline-db-press', 3, 10, 20),
      item('lateral-raise', 3, 15, 8, 60),
      item('triceps-pushdown', 3, 12, 25, 60),
    ],
  },
  {
    id: 'upper-pull',
    name: 'Upper Body Pull',
    short: 'Pull',
    category: 'upper',
    focus: 'Hypertrophy',
    level: 'intermediate',
    minutes: 45,
    summary: 'Vertical and horizontal pulling for a stronger back, finished with rear delts and grip.',
    exercises: [
      item('pull-up', 4, 6, 0, 120),
      item('barbell-row', 4, 8, 55, 120),
      item('seated-cable-row', 3, 12, 45),
      item('face-pull', 3, 15, 15, 60),
      item('hammer-curl', 3, 12, 12, 60),
    ],
  },
  {
    id: 'lower-strength',
    name: 'Lower Body Strength',
    short: 'Legs',
    category: 'lower',
    focus: 'Strength',
    level: 'advanced',
    minutes: 60,
    summary: 'Five heavy sets of squats, then hinge and single-leg work. Brace hard on every rep.',
    exercises: [
      item('back-squat', 5, 5, 80, 180),
      item('romanian-deadlift', 4, 8, 70, 120),
      item('split-squat', 3, 10, 16),
      item('leg-curl', 3, 12, 35, 60),
      item('calf-raise', 4, 15, 40, 60),
    ],
  },
  {
    id: 'leg-volume',
    name: 'Leg Volume',
    short: 'Legs',
    category: 'lower',
    focus: 'Hypertrophy',
    level: 'intermediate',
    minutes: 55,
    summary: 'Machine-led quad and hamstring volume in the 10–15 rep range. Chase the pump, not max load.',
    exercises: [
      item('leg-press', 4, 12, 120),
      item('walking-lunge', 3, 12, 14),
      item('leg-extension', 3, 15, 40, 60),
      item('leg-curl', 3, 12, 35, 60),
      item('calf-raise', 4, 15, 40, 60),
    ],
  },
  {
    id: 'full-foundations',
    name: 'Full-Body Foundations',
    short: 'Full',
    category: 'full',
    focus: 'Strength',
    level: 'beginner',
    minutes: 40,
    summary: 'Squat, push, pull and brace in one session. A solid base for your first months of training.',
    exercises: [
      item('goblet-squat', 3, 10, 16),
      item('push-up', 3, 10),
      item('db-row', 3, 10, 14),
      item('glute-bridge', 3, 12),
      item('plank', 3, 40, 0, 45),
    ],
  },
  {
    id: 'kettlebell-complex',
    name: 'Kettlebell Complex',
    short: 'KB',
    category: 'full',
    focus: 'Conditioning',
    level: 'intermediate',
    minutes: 30,
    summary: 'One bell, five movements, minimal rest. Builds power and work capacity in half an hour.',
    exercises: [
      item('kb-swing', 5, 12, 24, 60),
      item('goblet-squat', 4, 10, 24, 60),
      item('kb-clean-press', 4, 6, 16, 60),
      item('farmer-carry', 3, 40, 24, 60),
    ],
  },
  {
    id: 'hiit-engine',
    name: 'HIIT Engine',
    short: 'HIIT',
    category: 'conditioning',
    focus: 'Conditioning',
    level: 'advanced',
    minutes: 25,
    summary: 'All-out sprints with short recoveries. Expect RPE 9 by the last round.',
    exercises: [
      item('bike-sprint', 8, 20, 0, 40),
      item('kb-swing', 4, 15, 20, 45),
      item('burpee', 4, 10, 0, 45),
      item('mountain-climber', 4, 30, 0, 30),
    ],
  },
  {
    id: 'zone2-run',
    name: 'Zone 2 Run',
    short: 'Run',
    category: 'conditioning',
    focus: 'Endurance',
    level: 'beginner',
    minutes: 40,
    summary: 'Conversational pace for the whole run. You should be able to speak in full sentences.',
    exercises: [item('easy-run', 1, 35 * 60, 0, 0), item('hip-90-90', 2, 10, 0, 30)],
  },
  {
    id: 'core-stability',
    name: 'Core Stability',
    short: 'Core',
    category: 'core',
    focus: 'Stability',
    level: 'beginner',
    minutes: 20,
    summary: 'Anti-extension and anti-rotation work that carries over to every heavy lift.',
    exercises: [
      item('dead-bug', 3, 10, 0, 45),
      item('side-plank', 3, 30, 0, 30),
      item('pallof-press', 3, 12, 10, 45),
      item('hollow-hold', 3, 20, 0, 45),
    ],
  },
  {
    id: 'mobility-flow',
    name: 'Mobility Flow',
    short: 'Mobility',
    category: 'mobility',
    focus: 'Mobility',
    level: 'beginner',
    minutes: 20,
    summary: 'Hips, spine and shoulders. A low-effort session for rest days or before lifting.',
    exercises: [
      item('worlds-greatest', 2, 6, 0, 20),
      item('hip-90-90', 2, 10, 0, 20),
      item('cat-cow', 2, 10, 0, 20),
      item('thoracic-rotation', 2, 8, 0, 20),
      item('couch-stretch', 2, 45, 0, 20),
    ],
  },
];

const exerciseById = new Map(EXERCISES.map((e) => [e.id, e]));
const workoutById = new Map(WORKOUTS.map((w) => [w.id, w]));

export const getExercise = (id) => exerciseById.get(id) ?? null;
export const getWorkout = (id) => workoutById.get(id) ?? null;
export const categoryLabel = (id) => CATEGORIES.find((c) => c.id === id)?.label ?? id;
export const groupLabel = (id) => MUSCLE_GROUPS.find((g) => g.id === id)?.label ?? id;
export const getLevel = (id) => LEVELS.find((l) => l.id === id) ?? LEVELS[0];

export const workoutSetCount = (workout) => workout.exercises.reduce((n, e) => n + e.sets, 0);

/** Muscle groups a workout trains, in the order the routine reaches them. */
export function workoutGroups(workout) {
  const groups = workout.exercises.map((item) => getExercise(item.exercise)?.group).filter(Boolean);
  return [...new Set(groups)];
}

/** "Upper body · Strength", without repeating a focus that matches the category. */
export function workoutKicker(workout) {
  const category = categoryLabel(workout.category);
  return category === workout.focus ? category : `${category} · ${workout.focus}`;
}

/** Routines that include a given exercise. */
export const workoutsUsing = (exerciseId) => WORKOUTS.filter((w) => w.exercises.some((e) => e.exercise === exerciseId));
