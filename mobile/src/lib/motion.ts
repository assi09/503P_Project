import { Easing } from 'react-native-reanimated';

// Motion eases out and settles without overshoot: bouncing reads as wobble on small widgets.
export const EASE_OUT = Easing.out(Easing.cubic);
export const DURATION = { fast: 160, normal: 240 };
export const TIMING = { duration: DURATION.normal, easing: EASE_OUT };
