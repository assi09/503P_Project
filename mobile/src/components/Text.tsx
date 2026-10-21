import { Text as RNText, type TextProps } from 'react-native';

import { type, useColors, type Colors } from '@/theme';

interface Props extends TextProps {
  variant?: keyof typeof type;
  color?: keyof Colors | (string & {});
}

/** Text in the app's type scale and colors. `color` is a theme role ("muted") or any color. */
export function Text({ variant = 'body', color = 'text', style, ...props }: Props) {
  const colors = useColors();
  const resolved = color in colors ? colors[color as keyof Colors] : color;
  return <RNText {...props} style={[type[variant], { color: resolved }, style]} />;
}
