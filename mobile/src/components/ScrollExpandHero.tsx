import { Ionicons } from '@expo/vector-icons';
import type { ReactNode } from 'react';
import {
  Image,
  StyleSheet,
  useWindowDimensions,
  View,
  type ImageSourcePropType,
} from 'react-native';
import Animated, {
  useAnimatedScrollHandler,
  useAnimatedStyle,
  useDerivedValue,
  useSharedValue,
} from 'react-native-reanimated';

import { Text } from '@/components/Text';
import { heroFrame } from '@/lib/hero';
import { radius, useColors } from '@/theme';

interface Props {
  image: ImageSourcePropType;
  title: [string, string]; // two lines that slide apart as the image grows
  eyebrow?: string;
  hint?: string;
  header?: ReactNode; // drawn over the hero, e.g. the brand and a sign-in button
  children: ReactNode; // the content that follows once the image fills the screen
}

/**
 * An image card that grows to fill the screen as you scroll, then gives way to the content.
 * The hero stays pinned while it grows; scrolling is never hijacked, so it behaves the same with
 * touch, a wheel or a trackpad, on phones and in the browser.
 */
export function ScrollExpandHero({ image, title, eyebrow, hint, header, children }: Props) {
  const colors = useColors();
  const { width, height } = useWindowDimensions();
  const distance = height * 0.9; // how far to scroll for the image to fill the screen
  const scrollY = useSharedValue(0);
  const onScroll = useAnimatedScrollHandler((event) => {
    scrollY.set(event.contentOffset.y);
  });

  // A derived value, not a helper function: styles only update for shared values they read.
  const progress = useDerivedValue(() => Math.min(Math.max(scrollY.get() / distance, 0), 1));

  const pinned = useAnimatedStyle(() => ({
    transform: [{ translateY: Math.min(Math.max(scrollY.get(), 0), distance) }],
  }));
  const backdrop = useAnimatedStyle(() => ({ opacity: 1 - progress.get() }));
  const card = useAnimatedStyle(() => {
    const frame = heroFrame(progress.get(), width, height);
    return {
      width: frame.width,
      height: frame.height,
      borderRadius: frame.radius,
      left: (width - frame.width) / 2,
      top: (height - frame.height) / 2,
    };
  });
  const shade = useAnimatedStyle(() => ({ opacity: 0.45 - progress.get() * 0.3 }));
  const left = useAnimatedStyle(() => ({
    transform: [{ translateX: -heroFrame(progress.get(), width, height).textShift }],
  }));
  const right = useAnimatedStyle(() => ({
    transform: [{ translateX: heroFrame(progress.get(), width, height).textShift }],
  }));
  const hintStyle = useAnimatedStyle(() => ({
    opacity: Math.max(0, 1 - progress.get() * 3),
  }));

  const titleSize = width >= 768 ? 64 : 42;
  const titleStyle = { fontSize: titleSize, lineHeight: titleSize * 1.08 };

  return (
    <Animated.ScrollView
      onScroll={onScroll}
      scrollEventThrottle={16}
      showsVerticalScrollIndicator={false}
      style={{ backgroundColor: colors.background }}
    >
      <View style={{ height: height + distance }}>
        <Animated.View style={[{ height, overflow: 'hidden' }, pinned]}>
          <Animated.View style={[StyleSheet.absoluteFill, backdrop]}>
            <Image source={image} blurRadius={24} resizeMode="cover" style={styles.fill} />
            <View style={[StyleSheet.absoluteFill, styles.backdropShade]} />
          </Animated.View>

          <Animated.View style={[styles.card, card]}>
            <Image source={image} resizeMode="cover" style={styles.fill} />
            <Animated.View style={[StyleSheet.absoluteFill, styles.cardShade, shade]} />
          </Animated.View>

          <View style={styles.titles} pointerEvents="none">
            {eyebrow && (
              <Animated.View style={left}>
                <Text variant="label" color="#FFFFFF" style={styles.shadow}>
                  {eyebrow}
                </Text>
              </Animated.View>
            )}
            <Animated.View style={left}>
              <Text variant="display" color="#FFFFFF" style={[titleStyle, styles.shadow]}>
                {title[0]}
              </Text>
            </Animated.View>
            <Animated.View style={right}>
              <Text variant="display" color="#FFFFFF" style={[titleStyle, styles.shadow]}>
                {title[1]}
              </Text>
            </Animated.View>
          </View>

          {hint && (
            <Animated.View style={[styles.hint, hintStyle]} pointerEvents="none">
              <Text variant="caption" color="#FFFFFF" style={styles.shadow}>
                {hint}
              </Text>
              <Ionicons name="chevron-down" size={18} color="#FFFFFF" />
            </Animated.View>
          )}

          {header}
        </Animated.View>
      </View>

      {/* The content slides up over the full-screen image. */}
      <View style={[styles.content, { backgroundColor: colors.background }]}>{children}</View>
    </Animated.ScrollView>
  );
}

const styles = StyleSheet.create({
  fill: { width: '100%', height: '100%' },
  backdropShade: { backgroundColor: 'rgba(0,0,0,0.35)' },
  card: {
    position: 'absolute',
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOpacity: 0.35,
    shadowRadius: 30,
    shadowOffset: { width: 0, height: 10 },
  },
  cardShade: { backgroundColor: '#000' },
  titles: {
    ...StyleSheet.absoluteFill,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
  },
  shadow: {
    textAlign: 'center',
    textShadowColor: 'rgba(0,0,0,0.45)',
    textShadowRadius: 12,
    textShadowOffset: { width: 0, height: 2 },
  },
  hint: {
    position: 'absolute',
    bottom: 40,
    left: 0,
    right: 0,
    alignItems: 'center',
    gap: 2,
  },
  content: {
    marginTop: -radius.xl,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
  },
});
