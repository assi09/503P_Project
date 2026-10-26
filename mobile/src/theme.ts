import { createContext, createElement, useContext, useMemo, useState, type ReactNode } from 'react';
import { useColorScheme } from 'react-native';

// "Track day": the warm cream, track orange and sky blue of the landing photos. Light is the
// default look; dark is the same roles on warm charcoal rather than blue-black.
const light = {
  background: '#F7F2EA',
  surface: '#FFFFFF',
  surfaceRaised: '#FFFDF9',
  text: '#1F1915',
  muted: '#6E645B',
  faint: '#A0958A', // tertiary text, axis labels
  border: '#E8DFD3',
  accent: '#CC4620', // track orange, deep enough for white text on it
  onAccent: '#FFFFFF', // text and icons on accent backgrounds
  accentSoft: '#FBE3D8',
  secondary: '#3D8FD1', // sky blue
  danger: '#B83227',
  warning: '#B7791F',
  chart: '#CC4620',
  chartHighlight: '#FBE3D8',
  track: '#EFE7DC', // empty part of rings and bars
};

const dark: typeof light = {
  background: '#17120F',
  surface: '#221B17',
  surfaceRaised: '#2B231E',
  text: '#F5EFE8',
  muted: '#A89C90',
  faint: '#6F655C',
  border: '#362C25',
  accent: '#FF7A4D',
  onAccent: '#1A0F0A',
  accentSoft: '#3A2219',
  secondary: '#6FB3EA',
  danger: '#FF6B5E',
  warning: '#F2B94B',
  chart: '#FF7A4D',
  chartHighlight: '#3A2219',
  track: '#2E2620',
};

export type Colors = typeof dark;
export type Scheme = 'dark' | 'light';

/** Colors per metric family: a solid color for lines and text, and a gradient pair for rings. */
export const METRIC_COLORS = {
  sleep: { dark: '#8FA8FF', light: '#4F6BD8', gradient: ['#4F6BD8', '#8FB8FF'] },
  activity: { dark: '#FF8A4D', light: '#D9531F', gradient: ['#E2552C', '#FFA65C'] },
  heart: { dark: '#FF6B86', light: '#D63A5A', gradient: ['#D63A5A', '#FF8FA0'] },
  recovery: { dark: '#7BCB6A', light: '#4E9A3A', gradient: ['#4E9A3A', '#A6DB7D'] },
  temperature: { dark: '#5CC8D6', light: '#1E8E9C', gradient: ['#1E8E9C', '#7FDCE6'] },
  nutrition: { dark: '#F2C14E', light: '#B98512', gradient: ['#E0A21C', '#F7D877'] },
  stress: { dark: '#C39BFF', light: '#7C4DCC', gradient: ['#7C4DCC', '#C9A6FF'] },
} as const;

export type MetricFamily = keyof typeof METRIC_COLORS;

const FAMILY_BY_METRIC: Record<string, MetricFamily> = {
  sleep_minutes: 'sleep',
  time_in_bed: 'sleep',
  sleep_efficiency: 'sleep',
  sleep_score: 'sleep',
  bedtime_hour: 'sleep',
  deep_sleep_minutes: 'sleep',
  light_sleep_minutes: 'sleep',
  rem_sleep_minutes: 'sleep',
  awake_in_bed_minutes: 'sleep',
  steps: 'activity',
  calories: 'activity',
  distance_km: 'activity',
  active_zone_minutes: 'activity',
  cardio_load: 'activity',
  sedentary_minutes: 'activity',
  lightly_active_minutes: 'activity',
  moderately_active_minutes: 'activity',
  very_active_minutes: 'activity',
  resting_hr: 'heart',
  hrv_ms: 'heart',
  respiratory_rate: 'heart',
  readiness: 'recovery',
  recovery_score: 'recovery',
  strain: 'activity',
  hr_zone_light_minutes: 'activity',
  hr_zone_moderate_minutes: 'activity',
  hr_zone_vigorous_minutes: 'activity',
  hr_zone_peak_minutes: 'activity',
  stress_score: 'stress',
  skin_temp_variation_c: 'temperature',
};

export function metricFamily(metric: string): MetricFamily | undefined {
  return FAMILY_BY_METRIC[metric];
}

export type ThemePreference = Scheme | 'system';

const ThemeContext = createContext<Scheme>('light');
const PreferenceContext = createContext<{
  preference: ThemePreference;
  setPreference: (preference: ThemePreference) => void;
}>({ preference: 'system', setPreference: () => {} });

const STORAGE_KEY = 'patterns.theme';

// Remembered in the browser only; native apps have no storage dependency yet and start from
// the device setting each launch.
function storedPreference(): ThemePreference | undefined {
  try {
    const value = globalThis.localStorage?.getItem(STORAGE_KEY);
    return value === 'light' || value === 'dark' || value === 'system' ? value : undefined;
  } catch {
    return undefined;
  }
}

function storePreference(preference: ThemePreference) {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, preference);
  } catch {
    // Private mode or blocked storage: the choice lasts until reload.
  }
}

/** Follows the device unless the person picked light or dark, which `useThemePreference` sets. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const system = useColorScheme();
  const [preference, setPreference] = useState<ThemePreference>(
    () => storedPreference() ?? 'system',
  );
  const scheme: Scheme =
    preference === 'system' ? (system === 'dark' ? 'dark' : 'light') : preference;
  const value = useMemo(
    () => ({
      preference,
      setPreference: (next: ThemePreference) => {
        setPreference(next);
        storePreference(next);
      },
    }),
    [preference],
  );
  return createElement(
    PreferenceContext.Provider,
    { value },
    createElement(ThemeContext.Provider, { value: scheme }, children),
  );
}

export function useThemePreference() {
  return useContext(PreferenceContext);
}

export function useScheme(): Scheme {
  return useContext(ThemeContext);
}

export function useColors(): Colors {
  return useScheme() === 'dark' ? dark : light;
}

/** The metric's solid color in the current scheme, falling back to the accent. */
export function useMetricColor(metric: string): string {
  const scheme = useScheme();
  const colors = useColors();
  const family = metricFamily(metric);
  return family ? METRIC_COLORS[family][scheme] : colors.accent;
}

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 };

/** Content never gets wider than this, so the app reads well on tablets and desktop browsers. */
export const CONTENT_WIDTH = 720;

export const column = { maxWidth: CONTENT_WIDTH, width: '100%', alignSelf: 'center' } as const;
export const radius = { sm: 10, md: 14, lg: 20, xl: 28, pill: 999 };

export const fonts = {
  regular: 'Inter_400Regular',
  medium: 'Inter_500Medium',
  semibold: 'Inter_600SemiBold',
  bold: 'Inter_700Bold',
} as const;

/** Text styles; numbers use tabular figures so values do not jump as they change. */
export const type = {
  // The day's key values, read at arm's length.
  hero: {
    fontFamily: fonts.bold,
    fontSize: 44,
    lineHeight: 48,
    letterSpacing: -1.2,
    fontVariant: ['tabular-nums' as const],
  },
  display: { fontFamily: fonts.bold, fontSize: 34, lineHeight: 40, letterSpacing: -0.6 },
  title: { fontFamily: fonts.bold, fontSize: 24, lineHeight: 30, letterSpacing: -0.4 },
  headline: { fontFamily: fonts.semibold, fontSize: 17, lineHeight: 22, letterSpacing: -0.2 },
  body: { fontFamily: fonts.regular, fontSize: 15, lineHeight: 21 },
  bodyStrong: { fontFamily: fonts.semibold, fontSize: 15, lineHeight: 21 },
  caption: { fontFamily: fonts.medium, fontSize: 13, lineHeight: 17 },
  label: {
    fontFamily: fonts.semibold,
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 0.6,
    textTransform: 'uppercase' as const,
  },
  number: {
    fontFamily: fonts.bold,
    fontSize: 28,
    lineHeight: 32,
    letterSpacing: -0.5,
    fontVariant: ['tabular-nums' as const],
  },
};
