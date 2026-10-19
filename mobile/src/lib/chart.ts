import type { Point, Window } from '@/api/types';

export interface ChartGeometry {
  paths: string[]; // one SVG path per run of consecutive days with data
  highlight: { x: number; width: number } | null;
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
): ChartGeometry {
  const values = points.map((p) => p.value).filter((v): v is number => v !== null);
  if (points.length === 0 || values.length === 0 || width <= 0 || height <= 0) {
    return { paths: [], highlight: null, min: 0, max: 0 };
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1; // flat series sit in the middle
  const step = points.length > 1 ? (width - 2 * padding) / (points.length - 1) : 0;
  const x = (i: number) => padding + i * step;
  const y = (v: number) =>
    max === min ? height / 2 : padding + (1 - (v - min) / span) * (height - 2 * padding);

  const paths: string[] = [];
  let current = '';
  points.forEach((point, i) => {
    if (point.value === null) {
      if (current) paths.push(current);
      current = '';
      return;
    }
    const coords = `${round(x(i))},${round(y(point.value))}`;
    current = current ? `${current} L${coords}` : `M${coords}`;
  });
  if (current) paths.push(current);

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
  return { paths, highlight: band, min, max };
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
