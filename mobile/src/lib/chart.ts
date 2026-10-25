import type { Point, Window } from '@/api/types';

export interface ChartGeometry {
  paths: string[]; // one SVG path per run of consecutive days with data
  areas: string[]; // the same runs closed down to the bottom edge, for a filled area
  highlight: { x: number; width: number } | null;
  band: { y: number; height: number } | null; // the usual range, as a horizontal strip
  coords: ({ x: number; y: number } | null)[]; // each day's point, null on days without data
  min: number;
  max: number;
}

/**
 * Lays out a daily series in a `width` x `height` box. Days without data break the line instead of
 * being interpolated, so gaps stay visible. `padding` keeps the stroke inside the box.
 */
export function chartGeometry(
  points: Point[],
  width: number,
  height: number,
  highlight?: Window,
  padding = 2,
  usual?: { low: number; high: number },
): ChartGeometry {
  const values = points.map((p) => p.value).filter((v): v is number => v !== null);
  if (points.length === 0 || values.length === 0 || width <= 0 || height <= 0) {
    return { paths: [], areas: [], highlight: null, band: null, coords: [], min: 0, max: 0 };
  }
  // The usual range stays in view even when every value sits above or below it.
  const min = Math.min(...values, ...(usual ? [usual.low] : []));
  const max = Math.max(...values, ...(usual ? [usual.high] : []));
  const span = max - min || 1; // flat series sit in the middle
  const step = points.length > 1 ? (width - 2 * padding) / (points.length - 1) : 0;
  const x = (i: number) => padding + i * step;
  const y = (v: number) =>
    max === min ? height / 2 : padding + (1 - (v - min) / span) * (height - 2 * padding);

  const paths: string[] = [];
  const areas: string[] = [];
  let current = '';
  let runStart = 0;
  const close = (end: number) => {
    paths.push(current);
    areas.push(`${current} L${round(x(end))},${height} L${round(x(runStart))},${height} Z`);
  };
  points.forEach((point, i) => {
    if (point.value === null) {
      if (current) close(i - 1);
      current = '';
      return;
    }
    const coords = `${round(x(i))},${round(y(point.value))}`;
    if (!current) runStart = i;
    current = current ? `${current} L${coords}` : `M${coords}`;
  });
  if (current) close(points.length - 1);

  let band: ChartGeometry['highlight'] = null;
  if (highlight) {
    const first = points.findIndex((p) => p.date >= highlight.start);
    const last = findLastIndex(points, (p) => p.date <= highlight.end);
    if (first !== -1 && last >= first) {
      const left = first === 0 ? 0 : x(first) - step / 2;
      const right = last === points.length - 1 ? width : x(last) + step / 2;
      band = { x: round(left), width: round(right - left) };
    }
  }
  const usualBand = usual
    ? { y: round(y(usual.high)), height: round(Math.max(1, y(usual.low) - y(usual.high))) }
    : null;
  const coords = points.map((p, i) =>
    p.value === null ? null : { x: round(x(i)), y: round(y(p.value)) },
  );
  return { paths, areas, highlight: band, band: usualBand, coords, min, max };
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}

function findLastIndex<T>(items: T[], predicate: (item: T) => boolean): number {
  for (let i = items.length - 1; i >= 0; i--) {
    if (predicate(items[i])) return i;
  }
  return -1;
}
