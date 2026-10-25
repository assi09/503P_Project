import { useWindowDimensions } from 'react-native';

/** Wide enough for two columns side by side: tablets in landscape and desktop browsers. */
export const WIDE_MIN = 960;
export const WIDE_CONTENT = 1120;

export function useWide(): boolean {
  return useWindowDimensions().width >= WIDE_MIN;
}
