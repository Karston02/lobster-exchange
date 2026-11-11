// Turning a time into a horizontal position and back.
//
// The chart lays bars out by index ("logical" position: bar 0, 1, 2, ...), not
// by time: nights and weekends take no space. So a drawing's time becomes a
// fractional bar index: a time between two bars sits proportionally between
// them, and a time past either end continues at one bar per period. Going back
// reverses the same rule, so dragging round-trips cleanly. Because points are
// stored as times, the same drawing lands correctly on every timeframe.

/** `times` must be ascending (the bars' start times). */
export function timeToLogical(times: number[], periodS: number, time: number): number {
  const n = times.length;
  if (n === 0) return 0;
  if (time <= times[0]) return (time - times[0]) / periodS;
  if (time >= times[n - 1]) return n - 1 + (time - times[n - 1]) / periodS;
  let lo = 0;
  let hi = n - 1; // times[lo] <= time < times[hi]
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (times[mid] <= time) lo = mid;
    else hi = mid;
  }
  return lo + (time - times[lo]) / (times[hi] - times[lo]);
}

export function logicalToTime(times: number[], periodS: number, logical: number): number {
  const n = times.length;
  if (n === 0) return 0;
  if (logical <= 0) return times[0] + logical * periodS;
  if (logical >= n - 1) return times[n - 1] + (logical - (n - 1)) * periodS;
  const i = Math.floor(logical);
  return times[i] + (logical - i) * (times[i + 1] - times[i]);
}
