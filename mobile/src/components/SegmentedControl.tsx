import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { useAnimatedStyle, withSpring } from 'react-native-reanimated';

import { Text } from '@/components/Text';
import { select } from '@/lib/haptics';
import { radius, useColors } from '@/theme';

interface Props<T extends string> {
  options: readonly T[];
  value: T;
  onChange: (value: T) => void;
  accessibilityLabel?: string;
}

/** A row of options with a sliding highlight, e.g. 7D / 30D / 90D / All. */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  accessibilityLabel,
}: Props<T>) {
  const colors = useColors();
  const [width, setWidth] = useState(0);
  const segment = options.length ? width / options.length : 0;
  const index = Math.max(0, options.indexOf(value));

  const indicator = useAnimatedStyle(() => ({
    width: segment,
    transform: [{ translateX: withSpring(index * segment, { damping: 20, stiffness: 260 }) }],
  }));

  return (
    <View
      accessibilityRole="tablist"
      accessibilityLabel={accessibilityLabel}
      onLayout={(event) => setWidth(event.nativeEvent.layout.width - 6)}
      style={[styles.container, { backgroundColor: colors.surfaceRaised }]}
    >
      {segment > 0 && (
        <Animated.View style={[styles.indicator, { backgroundColor: colors.track }, indicator]} />
      )}
      {options.map((option) => {
        const selected = option === value;
        return (
          <Pressable
            key={option}
            accessibilityRole="tab"
            accessibilityState={{ selected }}
            onPress={() => {
              if (!selected) {
                select();
                onChange(option);
              }
            }}
            style={styles.option}
          >
            <Text variant="caption" color={selected ? 'text' : 'muted'}>
              {option}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flexDirection: 'row', borderRadius: radius.md, padding: 3 },
  indicator: { position: 'absolute', top: 3, bottom: 3, left: 3, borderRadius: radius.sm },
  option: { flex: 1, alignItems: 'center', paddingVertical: 7 },
});
