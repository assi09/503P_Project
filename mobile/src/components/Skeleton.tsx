import { useEffect } from 'react';
import type { DimensionValue, StyleProp, ViewStyle } from 'react-native';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';

import { radius as radii, useColors } from '@/theme';

interface Props {
  width?: DimensionValue;
  height: number;
  radius?: number;
  style?: StyleProp<ViewStyle>;
}

/** A gently pulsing placeholder shown while content loads, in place of a spinner. */
export function Skeleton({ width = '100%', height, radius = radii.md, style }: Props) {
  const colors = useColors();
  const opacity = useSharedValue(0.5);

  useEffect(() => {
    opacity.set(
      withRepeat(withTiming(1, { duration: 800, easing: Easing.inOut(Easing.quad) }), -1, true),
    );
  }, [opacity]);

  const animated = useAnimatedStyle(() => ({ opacity: opacity.value }));
  return (
    <Animated.View
      accessibilityLabel="Loading"
      style={[{ width, height, borderRadius: radius, backgroundColor: colors.surfaceRaised }, animated, style]}
    />
  );
}
