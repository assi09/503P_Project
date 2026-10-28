import { Ionicons } from '@expo/vector-icons';
import type { ReactNode } from 'react';
import {
  Image,
  Platform,
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

const WEB = Platform.OS === 'web';

interface Props {
  image: ImageSourcePropType;
  imageSize: { width: number; height: number }; // its pixels, to crop it like `cover` while scaling
  background?: ImageSourcePropType; // behind the card; without one, a blurred copy of `image`
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
 *
 * In browsers only transforms and opacity follow the scroll. Safari on phones scrolls on its own
 * thread and hands the page scroll events late, so a hero pinned by moving it with JavaScript, or
 * a card grown by changing its size, trails the finger and stutters there. The browser pins the
 * hero itself (`position: sticky`), and the card grows by scaling, with the photo inside scaled
 * back so it is never stretched.
 */
export function ScrollExpandHero({
  image,
  imageSize,
  background,
  title,
  eyebrow,
  hint,
  header,
  children,
}: Props) {
  const colors = useColors();
  const { width, height } = useWindowDimensions();
  const distance = height * 0.9; // how far to scroll for the image to fill the screen
  const scrollY = useSharedValue(0);
  const onScroll = useAnimatedScrollHandler((event) => {
    scrollY.set(event.contentOffset.y);
  });

  // A derived value, not a helper function: styles only update for shared values they read.
  const progress = useDerivedValue(() => Math.min(Math.max(scrollY.get() / distance, 0), 1));

  // Native apps animate on the UI thread, in step with the scroll; browsers pin it in CSS.
  const pinned = useAnimatedStyle(() =>
    WEB ? {} : { transform: [{ translateY: Math.min(Math.max(scrollY.get(), 0), distance) }] },
  );
  const backdrop = useAnimatedStyle(() => ({ opacity: 1 - progress.get() }));
  const card = useAnimatedStyle(() => {
    const frame = heroFrame(progress.get(), width, height);
    if (WEB) {
      // A full-screen box scaled down around its centre to the card's size.
      const x = frame.width / width;
      const y = frame.height / height;
      return { transform: [{ scaleX: x }, { scaleY: y }], borderRadius: frame.radius / x };
    }
    return {
      width: frame.width,
      height: frame.height,
      borderRadius: frame.radius,
      left: (width - frame.width) / 2,
      top: (height - frame.height) / 2,
    };
  });
  // The photo undoes the card's stretch, then shrinks to cover the card as `cover` would at that
  // size: by how much less it must grow to cover the card than to cover the whole screen.
  const photo = useAnimatedStyle(() => {
    if (!WEB) return {};
    const frame = heroFrame(progress.get(), width, height);
    const cover = (w: number, h: number) => Math.max(w / imageSize.width, h / imageSize.height);
    const fit = cover(frame.width, frame.height) / cover(width, height);
    return {
      transform: [
        { scaleX: (fit * width) / frame.width },
        { scaleY: (fit * height) / frame.height },
      ],
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

  // In browsers the photo is laid out whole at the size that covers the screen, centred, so the
  // card's clip, not the photo's own bounds, decides what shows at every size.
  const screenCover = Math.max(width / imageSize.width, height / imageSize.height);
  const whole = {
    position: 'absolute' as const,
    width: imageSize.width * screenCover,
    height: imageSize.height * screenCover,
    left: (width - imageSize.width * screenCover) / 2,
    top: (height - imageSize.height * screenCover) / 2,
  };

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
        <Animated.View
          style={[{ height, overflow: 'hidden' }, styles.layer, WEB && styles.sticky, pinned]}
        >
          <Animated.View style={[StyleSheet.absoluteFill, styles.fade, backdrop]}>
            <Image
              source={background ?? image}
              blurRadius={background ? 0 : 24}
              resizeMode="cover"
              style={styles.fill}
            />
            <View style={[StyleSheet.absoluteFill, styles.backdropShade]} />
          </Animated.View>

          <Animated.View
            style={[
              styles.card,
              styles.cardShadow,
              WEB && { width, height, left: 0, top: 0 },
              card,
            ]}
          >
            <Animated.View style={[WEB ? whole : styles.fill, styles.layer, photo]}>
              <Image source={image} resizeMode="cover" style={styles.fill} />
            </Animated.View>
            <Animated.View style={[StyleSheet.absoluteFill, styles.cardShade, shade]} />
          </Animated.View>

          <View style={styles.titles} pointerEvents="none">
            {eyebrow && (
              <Animated.View style={[styles.layer, left]}>
                <Text variant="label" color="#FFFFFF" style={styles.shadow}>
                  {eyebrow}
                </Text>
              </Animated.View>
            )}
            <Animated.View style={[styles.layer, left]}>
              <Text variant="display" color="#FFFFFF" style={[titleStyle, styles.shadow]}>
                {title[0]}
              </Text>
            </Animated.View>
            <Animated.View style={[styles.layer, right]}>
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
  card: { position: 'absolute', overflow: 'hidden' },
  // A large soft shadow is repainted on every frame the card grows, which is slow in Safari's
  // engine; the browsers go without it. Moving layers get their own compositor layer there too.
  cardShadow: Platform.select({
    web: {},
    default: {
      shadowColor: '#000',
      shadowOpacity: 0.35,
      shadowRadius: 30,
      shadowOffset: { width: 0, height: 10 },
    },
  }),
  layer: Platform.select({ web: { willChange: 'transform' } as object, default: {} }),
  fade: Platform.select({ web: { willChange: 'opacity' } as object, default: {} }),
  // The browser keeps the hero in view while its 0.9 screens of scroll pass (web only).
  sticky: { position: 'sticky', top: 0 } as object,
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
