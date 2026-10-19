import { useColorScheme } from 'react-native';

const light = {
  background: '#F6F7F9',
  surface: '#FFFFFF',
  text: '#14171F',
  muted: '#5F6675',
  border: '#E3E6EB',
  accent: '#2A6FDB',
  accentSoft: '#E5EEFC',
  up: '#1E8E5A',
  down: '#C2410C',
  warning: '#B45309',
  chart: '#2A6FDB',
  chartHighlight: '#E5EEFC',
};

const dark: typeof light = {
  background: '#0E1015',
  surface: '#181B22',
  text: '#ECEEF2',
  muted: '#9AA1AF',
  border: '#2A2F3A',
  accent: '#6EA2F5',
  accentSoft: '#1D2A40',
  up: '#4CC38A',
  down: '#F0884D',
  warning: '#E3A008',
  chart: '#6EA2F5',
  chartHighlight: '#1D2A40',
};

export type Colors = typeof light;

export function useColors(): Colors {
  return useColorScheme() === 'dark' ? dark : light;
}

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 };
export const radius = { sm: 8, md: 12, lg: 16 };
