import { Ionicons } from '@expo/vector-icons';
import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  TextInput,
  View,
  useWindowDimensions,
  type NativeSyntheticEvent,
  type TextInputKeyPressEventData,
} from 'react-native';
import Animated, {
  FadeIn,
  LinearTransition,
  interpolate,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Rect } from 'react-native-svg';

import type { Depth, ExpertChoice } from '@/api/types';
import { PressableScale } from '@/components/PressableScale';
import { Text } from '@/components/Text';
import { EXPERTS, expertInfo, useExpertColor, type ExpertInfo } from '@/lib/experts';
import { select, tap } from '@/lib/haptics';
import { DURATION, EASE_OUT, TIMING } from '@/lib/motion';
import { fonts, radius, spacing, type, useColors } from '@/theme';

const LABEL_LAYOUT = LinearTransition.duration(DURATION.fast).easing(EASE_OUT);

const PILL_HEIGHT = 48;
const PILL_WIDTH = 320;
const CONTROLS_HEIGHT = 46; // the row of controls under the text
const MIN_TEXT = 46;
const MAX_TEXT = 140;
const TAB_HEIGHT = 36; // the attachment tab that slides up from behind the input
const MENU_WIDTH = 272;

interface ComposerProps {
  value: string;
  onChangeText: (value: string) => void;
  onSubmit: () => void;
  expert: ExpertChoice;
  onExpertChange: (expert: ExpertChoice) => void;
  depth: Depth;
  onDepthChange: (depth: Depth) => void;
  attachmentLabel?: string;
  onAttach: () => void;
  onClearAttachment: () => void;
  busy: boolean;
  /** Shrinks to a pill while empty and not focused, e.g. on the empty chat. */
  collapsible: boolean;
  placeholder: string;
  maxLength: number;
}

/** The chat input: a pill that opens into a card with the expert, depth and attach controls. */
export function Composer({
  value,
  onChangeText,
  onSubmit,
  expert,
  onExpertChange,
  depth,
  onDepthChange,
  attachmentLabel,
  onAttach,
  onClearAttachment,
  busy,
  collapsible,
  placeholder,
  maxLength,
}: ComposerProps) {
  const colors = useColors();
  const input = useRef<TextInput>(null);
  // Set when a control is pressed, so the blur that the press causes does not close the input.
  const keepOpen = useRef(false);
  const [focused, setFocused] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const hasContent = value.trim().length > 0 || attachmentLabel !== undefined;
  const open = !collapsible || focused || hasContent || menuOpen;
  const canSend = value.trim().length > 0 && !busy;

  const progress = useSharedValue(open ? 1 : 0);
  const textHeight = useSharedValue(MIN_TEXT);
  const available = useSharedValue(0);
  const tab = useSharedValue(attachmentLabel && open ? 1 : 0);

  useEffect(() => {
    progress.set(withTiming(open ? 1 : 0, TIMING));
  }, [open, progress]);
  useEffect(() => {
    tab.set(withTiming(attachmentLabel && open ? 1 : 0, TIMING));
  }, [attachmentLabel, open, tab]);
  useEffect(() => {
    // The web reports a text box's content as at least its current height, so it never shrinks
    // on its own; start small again once the text is cleared, e.g. after sending.
    if (value === '') textHeight.set(withTiming(MIN_TEXT, { duration: 150 }));
  }, [value, textHeight]);

  const cardStyle = useAnimatedStyle(() => {
    const height = interpolate(progress.value, [0, 1], [PILL_HEIGHT, textHeight.value + CONTROLS_HEIGHT]);
    if (!available.value) return { height };
    const pill = Math.min(PILL_WIDTH, available.value);
    const width = interpolate(progress.value, [0, 1], [pill, available.value]);
    return { height, width };
  });
  const openStyle = useAnimatedStyle(() => ({
    opacity: Math.min(1, Math.max(0, progress.value)),
    transform: [{ translateY: (1 - progress.value) * 6 }],
  }));
  const pillStyle = useAnimatedStyle(() => ({
    opacity: Math.min(1, Math.max(0, 1 - progress.value * 1.6)),
  }));
  const textStyle = useAnimatedStyle(() => ({ height: textHeight.value }));
  const tabStyle = useAnimatedStyle(() => ({
    height: Math.max(0, tab.value) * (TAB_HEIGHT - 8),
  }));
  const tabInnerStyle = useAnimatedStyle(() => ({
    opacity: Math.min(1, Math.max(0, tab.value)),
    transform: [{ translateY: (1 - tab.value) * TAB_HEIGHT }],
  }));

  function openInput() {
    tap();
    setFocused(true);
    setTimeout(() => input.current?.focus(), 60);
  }

  function handleBlur() {
    setTimeout(() => {
      if (keepOpen.current) {
        keepOpen.current = false;
        return;
      }
      setFocused(false);
    }, 150);
  }

  function handleKeyPress(event: NativeSyntheticEvent<TextInputKeyPressEventData>) {
    // On the web, Enter sends and Shift+Enter adds a line; phones use the send button.
    const shift = (event.nativeEvent as unknown as { shiftKey?: boolean }).shiftKey;
    if (Platform.OS === 'web' && event.nativeEvent.key === 'Enter' && !shift) {
      event.preventDefault();
      if (canSend) onSubmit();
    }
  }

  const holdOpen = () => {
    keepOpen.current = true;
  };

  return (
    <View
      style={styles.wrapper}
      onLayout={(event) => available.set(event.nativeEvent.layout.width)}
    >
      <Animated.View style={[styles.tabTrack, tabStyle]}>
        {attachmentLabel !== undefined && (
          <Animated.View
            style={[
              styles.tab,
              { backgroundColor: colors.surfaceRaised, borderColor: colors.border },
              tabInnerStyle,
            ]}
          >
            <Ionicons name="pricetag" size={12} color={colors.accent} />
            <Text variant="caption" color="accent" numberOfLines={1} style={{ flex: 1 }}>
              {attachmentLabel}
            </Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Remove attachment"
              hitSlop={10}
              onPressIn={holdOpen}
              onPress={onClearAttachment}
            >
              <Ionicons name="close" size={15} color={colors.muted} />
            </Pressable>
          </Animated.View>
        )}
      </Animated.View>

      <Animated.View
        style={[
          styles.card,
          { backgroundColor: colors.surface, borderColor: focused ? colors.faint : colors.border },
          cardStyle,
        ]}
      >
        <Animated.View style={[styles.textBox, textStyle, openStyle]} pointerEvents={open ? 'auto' : 'none'}>
          <TextInput
            ref={input}
            value={value}
            onChangeText={onChangeText}
            onFocus={() => setFocused(true)}
            onBlur={handleBlur}
            onKeyPress={handleKeyPress}
            onContentSizeChange={(event) => {
              const height = Math.min(MAX_TEXT, Math.max(MIN_TEXT, event.nativeEvent.contentSize.height));
              textHeight.set(withTiming(height, { duration: 150 }));
            }}
            placeholder={placeholder}
            placeholderTextColor={colors.faint}
            maxLength={maxLength}
            multiline
            scrollEnabled
            style={[styles.input, { color: colors.text }]}
            accessibilityLabel="Message"
          />
        </Animated.View>

        {!open && (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Write a message"
            onPress={openInput}
            style={StyleSheet.absoluteFill}
          >
            <Animated.View style={[styles.pill, pillStyle]}>
              <Text color="faint" numberOfLines={1} style={{ fontFamily: fonts.medium }}>
                {placeholder}
              </Text>
            </Animated.View>
          </Pressable>
        )}

        <Animated.View
          style={[styles.controls, openStyle]}
          pointerEvents={open ? 'box-none' : 'none'}
        >
          <ExpertPicker
            value={expert}
            onChange={onExpertChange}
            onPressIn={holdOpen}
            onOpenChange={setMenuOpen}
          />
          <PressableScale
            accessibilityRole="button"
            accessibilityLabel={`Answer depth: ${depth}. Double tap to change.`}
            onPressIn={holdOpen}
            onPress={() => {
              select();
              onDepthChange(depth === 'quick' ? 'deep' : 'quick');
            }}
            haptic={false}
            style={styles.control}
          >
            <DepthIcon depth={depth} color={colors.muted} />
            <MorphLabel text={depth === 'quick' ? 'Quick' : 'Deep'} color={colors.muted} />
          </PressableScale>
          <View style={{ flex: 1 }} />
          <PressableScale
            accessibilityRole="button"
            accessibilityLabel="Attach a finding or metric"
            onPressIn={holdOpen}
            onPress={onAttach}
            style={[styles.control, styles.attach]}
          >
            <Ionicons name="add" size={18} color={colors.muted} />
          </PressableScale>
        </Animated.View>

        {/* Positioned by a wrapper: PressableScale applies its style to an inner view. */}
        <View style={styles.sendSlot}>
          <PressableScale
            accessibilityRole="button"
            accessibilityLabel="Send"
            disabled={!canSend}
            onPressIn={holdOpen}
            onPress={onSubmit}
            scaleTo={0.9}
            style={[
              styles.send,
              { backgroundColor: canSend || busy ? colors.text : colors.surfaceRaised },
            ]}
          >
            {busy ? (
              <ActivityIndicator size="small" color={colors.background} />
            ) : (
              <Ionicons name="arrow-up" size={17} color={canSend ? colors.background : colors.faint} />
            )}
          </PressableScale>
        </View>
      </Animated.View>
    </View>
  );
}

/** A label that eases to its new width and fades the new text in when it changes. */
function MorphLabel({ text, color }: { text: string; color: string }) {
  return (
    <Animated.View layout={LABEL_LAYOUT} style={styles.morph}>
      <Animated.Text
        key={text}
        entering={FadeIn.duration(DURATION.fast)}
        numberOfLines={1}
        style={[type.caption, styles.controlText, { color }]}
      >
        {text}
      </Animated.Text>
    </Animated.View>
  );
}

/** Two bars; the second lights up for a deep answer. */
function DepthIcon({ depth, color }: { depth: Depth; color: string }) {
  return (
    <Svg width={14} height={14} viewBox="0 0 14 14">
      <Rect x={2.5} y={6} width={3} height={6.5} rx={1.2} fill={color} />
      <Rect x={8.5} y={2} width={3} height={10.5} rx={1.2} fill={color} opacity={depth === 'deep' ? 1 : 0.3} />
    </Svg>
  );
}

function ExpertPicker({
  value,
  onChange,
  onPressIn,
  onOpenChange,
}: {
  value: ExpertChoice;
  onChange: (expert: ExpertChoice) => void;
  onPressIn: () => void;
  onOpenChange: (open: boolean) => void;
}) {
  const colors = useColors();
  const color = useExpertColor(value);
  const info = expertInfo(value);
  const button = useRef<View>(null);
  const window = useWindowDimensions();
  const [anchor, setAnchor] = useState<{ x: number; y: number } | null>(null);

  function show() {
    button.current?.measureInWindow((x, y) => {
      setAnchor({ x, y });
      onOpenChange(true);
    });
  }

  function close() {
    setAnchor(null);
    onOpenChange(false);
  }

  return (
    <>
      <View ref={button} collapsable={false}>
        <PressableScale
          accessibilityRole="button"
          accessibilityLabel={`Expert: ${info.label}. Double tap to change.`}
          onPressIn={onPressIn}
          onPress={show}
          style={[styles.control, anchor && { backgroundColor: colors.surfaceRaised }]}
        >
          <Ionicons name={info.icon} size={14} color={color} />
          <MorphLabel text={info.label} color={colors.text} />
          <Ionicons name="chevron-down" size={12} color={colors.faint} />
        </PressableScale>
      </View>

      <Modal visible={anchor !== null} transparent animationType="none" onRequestClose={close}>
        <Pressable style={StyleSheet.absoluteFill} onPress={close} accessibilityLabel="Close" />
        {anchor && (
          <Animated.View
            entering={FadeIn.duration(DURATION.fast)}
            style={[
              styles.menu,
              {
                left: Math.max(spacing.sm, Math.min(anchor.x, window.width - MENU_WIDTH - spacing.sm)),
                bottom: window.height - anchor.y + spacing.sm,
                backgroundColor: colors.surfaceRaised,
                borderColor: colors.border,
              },
            ]}
          >
            {EXPERTS.map((expert) => (
              <ExpertRow
                key={expert.id}
                expert={expert}
                selected={expert.id === value}
                onPress={() => {
                  select();
                  onChange(expert.id);
                  close();
                }}
              />
            ))}
          </Animated.View>
        )}
      </Modal>
    </>
  );
}

function ExpertRow({
  expert,
  selected,
  onPress,
}: {
  expert: ExpertInfo;
  selected: boolean;
  onPress: () => void;
}) {
  const colors = useColors();
  const color = useExpertColor(expert.id);
  return (
    <PressableScale
      accessibilityRole="menuitem"
      accessibilityState={{ selected, disabled: !expert.available }}
      disabled={!expert.available}
      haptic={false}
      onPress={onPress}
      style={[styles.row, selected && { backgroundColor: colors.surface }]}
    >
      <View style={[styles.rowIcon, { backgroundColor: `${color}22` }]}>
        <Ionicons name={expert.icon} size={15} color={color} />
      </View>
      <View style={{ flex: 1 }}>
        <Text variant="bodyStrong" style={{ fontSize: 14 }}>
          {expert.label}
        </Text>
        <Text variant="caption" color="muted" numberOfLines={1} style={{ fontSize: 12 }}>
          {expert.description}
        </Text>
      </View>
      {selected && (
        <Animated.View entering={FadeIn}>
          <Ionicons name="checkmark" size={16} color={colors.text} />
        </Animated.View>
      )}
      {!expert.available && (
        <View style={[styles.soon, { backgroundColor: colors.surface }]}>
          <Text variant="caption" color="muted" style={{ fontSize: 11 }}>
            Soon
          </Text>
        </View>
      )}
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  wrapper: { width: '100%', alignItems: 'center' },
  tabTrack: { width: '100%', overflow: 'hidden', paddingHorizontal: 18, zIndex: 0 },
  tab: {
    height: TAB_HEIGHT,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: spacing.md,
    paddingBottom: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: 0,
    borderTopLeftRadius: radius.md,
    borderTopRightRadius: radius.md,
  },
  card: {
    width: '100%',
    borderRadius: 24,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: 'hidden',
    zIndex: 1,
  },
  textBox: { position: 'absolute', top: 0, left: 0, right: 0 },
  input: {
    flex: 1,
    paddingLeft: spacing.lg,
    paddingRight: 52,
    paddingTop: 13,
    paddingBottom: 6,
    fontSize: 15,
    lineHeight: 21,
    fontFamily: fonts.regular,
    textAlignVertical: 'top',
    // The web adds a focus ring and resize handle that do not belong in this design.
    ...(Platform.OS === 'web' && ({ outlineStyle: 'none', resize: 'none' } as object)),
  },
  pill: {
    flex: 1,
    justifyContent: 'center',
    paddingLeft: spacing.lg,
    paddingRight: 52,
  },
  controls: {
    position: 'absolute',
    left: spacing.sm,
    right: 52,
    bottom: 8,
    height: 32,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
  },
  control: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    height: 30,
    paddingHorizontal: 9,
    borderRadius: radius.pill,
  },
  controlText: { fontFamily: fonts.semibold, fontSize: 12 },
  morph: { overflow: 'hidden' },
  attach: { width: 30, paddingHorizontal: 0, justifyContent: 'center' },
  sendSlot: { position: 'absolute', right: 8, bottom: 8 },
  send: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  menu: {
    position: 'absolute',
    width: MENU_WIDTH,
    padding: 5,
    gap: 2,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    shadowColor: '#000',
    shadowOpacity: 0.35,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 12 },
    elevation: 12,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 7,
    borderRadius: radius.md,
  },
  rowIcon: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
  },
  soon: { paddingHorizontal: 7, paddingVertical: 2, borderRadius: radius.pill },
});
