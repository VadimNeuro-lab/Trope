// Weights are always stored in kilograms and converted only for display and input.

export const KG_PER_LB = 0.45359237;

const grouped = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 });

export const formatNumber = (n) => grouped.format(n);

/** Kilograms → the number shown in the user's unit (kg to the nearest 0.5, lb to the nearest 1). */
export function toDisplayWeight(kg, units) {
  if (units === 'lb') return Math.round(kg / KG_PER_LB);
  return Math.round(kg * 2) / 2;
}

/** A number typed in the user's unit → kilograms, kept to two decimals. */
export function fromDisplayWeight(value, units) {
  const kg = units === 'lb' ? value * KG_PER_LB : value;
  return Math.round(kg * 100) / 100;
}

export const unitLabel = (units) => (units === 'lb' ? 'lb' : 'kg');

export const formatWeight = (kg, units) => `${formatNumber(toDisplayWeight(kg, units))} ${unitLabel(units)}`;

/** Total lifted load in the user's unit, rounded: decimals would only add noise. */
export const displayVolume = (kg, units) => Math.round(units === 'lb' ? kg / KG_PER_LB : kg);

export const formatVolume = (kg, units) => `${formatNumber(displayVolume(kg, units))} ${unitLabel(units)}`;

/** Seconds as "45 s", "1:30" or "35 min". */
export function formatDuration(seconds) {
  if (seconds < 90) return `${seconds} s`;
  if (seconds % 60 === 0) return `${seconds / 60} min`;
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

export function formatMinutes(minutes) {
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}
