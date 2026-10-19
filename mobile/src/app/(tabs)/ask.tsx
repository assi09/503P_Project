import { Ionicons } from '@expo/vector-icons';
import { router, useLocalSearchParams } from 'expo-router';
import { BottomTabBarHeightContext } from 'expo-router/js-tabs';
import { useContext, useEffect, useMemo, useRef, useState } from 'react';
import {
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useChat, useReport, useSendMessage } from '@/api/hooks';
import { MessageBubble, Thinking } from '@/components/chat';
import { PressableScale } from '@/components/PressableScale';
import { QueryState } from '@/components/Screen';
import { Text } from '@/components/Text';
import { Chip } from '@/components/ui';
import { floatingTabBar } from '@/lib/platform';
import { fonts, radius, spacing, useColors } from '@/theme';

const MAX_LENGTH = 500;

// Questions offered while a finding is attached.
const FINDING_SUGGESTIONS = ['Why did this happen?', 'What else changed around then?'];

const SUGGESTIONS = [
  'Why is my sleep worse lately?',
  'How are my steps trending?',
  'What changed most this month?',
];

export default function AskScreen() {
  const colors = useColors();
  const { findingId } = useLocalSearchParams<{ findingId?: string }>();
  const chat = useChat();
  const report = useReport();
  const send = useSendMessage();
  const [draft, setDraft] = useState('');
  const scroll = useRef<ScrollView>(null);
  const insets = useSafeAreaInsets();
  const barHeight = useContext(BottomTabBarHeightContext) ?? 0;
  const tabBarHeight = floatingTabBar ? barHeight : 0;
  const keyboardOpen = useKeyboardOpen();

  const finding = report.data?.findings.find((f) => f.id === findingId);
  const findingTitles = useMemo(
    () => Object.fromEntries((report.data?.findings ?? []).map((f) => [f.id, f.title])),
    [report.data],
  );
  const messages = chat.data ?? [];
  const pendingText = send.isPending ? send.variables?.text : undefined;
  const canSend = draft.trim().length > 0 && !send.isPending;

  useEffect(() => {
    scroll.current?.scrollToEnd({ animated: true });
  }, [messages.length, send.isPending]);

  function submit(text: string) {
    const trimmed = text.trim();
    if (!trimmed || send.isPending) return;
    send.mutate(
      { text: trimmed, findingId: finding?.id },
      { onSuccess: () => setDraft('') }, // keep the text if sending fails, so it can be retried
    );
  }

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.background }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Text variant="display" accessibilityRole="header">
          Ask
        </Text>
      </View>
      {finding && (
        <Animated.View
          entering={FadeIn}
          style={[styles.context, { backgroundColor: colors.accentSoft }]}
        >
          <Ionicons name="pricetag" size={13} color={colors.accent} />
          <Text variant="caption" color="accent" style={{ flex: 1 }} numberOfLines={1}>
            Asking about: {finding.title}
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Stop asking about this finding"
            hitSlop={8}
            onPress={() => router.setParams({ findingId: undefined })}
          >
            <Ionicons name="close" size={16} color={colors.accent} />
          </Pressable>
        </Animated.View>
      )}

      <ScrollView
        ref={scroll}
        contentContainerStyle={styles.messages}
        keyboardShouldPersistTaps="handled"
      >
        <QueryState query={chat}>
          {() =>
            messages.length === 0 && !pendingText ? (
              <View style={styles.empty}>
                <View style={[styles.emptyIcon, { backgroundColor: colors.accentSoft }]}>
                  <Ionicons name="sparkles" size={22} color={colors.accent} />
                </View>
                <Text variant="title">Ask about your data</Text>
                <Text color="muted">
                  Answers come from computations on your own Fitbit data, and each one shows what
                  it is based on. I describe patterns; I don&apos;t give medical advice.
                </Text>
                <View style={styles.suggestions}>
                  {(finding ? [...FINDING_SUGGESTIONS, ...SUGGESTIONS] : SUGGESTIONS).map((text) => (
                    <Chip key={text} label={text} onPress={() => submit(text)} />
                  ))}
                </View>
              </View>
            ) : (
              <>
                {messages.map((message) => (
                  <MessageBubble
                    key={message.id}
                    message={message}
                    knownEvidence={report.data?.evidence ?? {}}
                    findingTitles={findingTitles}
                  />
                ))}
                {pendingText && (
                  <>
                    <View
                      style={[
                        styles.pendingMine,
                        { backgroundColor: colors.surfaceRaised, borderColor: colors.border },
                      ]}
                    >
                      <Text>{pendingText}</Text>
                    </View>
                    <Thinking />
                  </>
                )}
              </>
            )
          }
        </QueryState>
        {send.error && (
          <Text variant="caption" color="danger" style={{ textAlign: 'center' }}>
            Could not send your message. Check your connection and try again.
          </Text>
        )}
      </ScrollView>

      {finding && messages.length > 0 && (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={styles.quickReplies}
        >
          {FINDING_SUGGESTIONS.map((text) => (
            <Chip key={text} label={text} disabled={send.isPending} onPress={() => submit(text)} />
          ))}
        </ScrollView>
      )}

      <View
        style={[
          styles.inputBar,
          // Above the floating tab bar, except while the keyboard covers it.
          { paddingBottom: (keyboardOpen ? 0 : tabBarHeight) + spacing.sm },
        ]}
      >
        <TextInput
          value={draft}
          onChangeText={setDraft}
          placeholder="Ask about your sleep, activity, heart…"
          placeholderTextColor={colors.faint}
          maxLength={MAX_LENGTH}
          multiline
          numberOfLines={1}
          style={[
            styles.input,
            { color: colors.text, backgroundColor: colors.surface, borderColor: colors.border },
          ]}
          accessibilityLabel="Message"
        />
        <PressableScale
          accessibilityRole="button"
          accessibilityLabel="Send"
          disabled={!canSend}
          onPress={() => submit(draft)}
          style={[styles.send, { backgroundColor: canSend ? colors.text : colors.surfaceRaised }]}
        >
          <Ionicons name="arrow-up" size={20} color={canSend ? colors.background : colors.faint} />
        </PressableScale>
      </View>
    </KeyboardAvoidingView>
  );
}

function useKeyboardOpen(): boolean {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const shown = Keyboard.addListener('keyboardWillShow', () => setOpen(true));
    const hidden = Keyboard.addListener('keyboardWillHide', () => setOpen(false));
    const shownAndroid = Keyboard.addListener('keyboardDidShow', () => setOpen(true));
    const hiddenAndroid = Keyboard.addListener('keyboardDidHide', () => setOpen(false));
    return () => [shown, hidden, shownAndroid, hiddenAndroid].forEach((s) => s.remove());
  }, []);
  return open;
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  context: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginHorizontal: spacing.lg,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
  },
  messages: {
    padding: spacing.lg,
    gap: spacing.md,
    flexGrow: 1,
    maxWidth: 720,
    width: '100%',
    alignSelf: 'center',
  },
  empty: { flex: 1, justifyContent: 'center', gap: spacing.md, paddingVertical: spacing.xl },
  emptyIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  suggestions: { gap: spacing.sm, alignItems: 'flex-start' },
  pendingMine: {
    alignSelf: 'flex-end',
    maxWidth: '82%',
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderRadius: radius.lg,
    borderBottomRightRadius: 6,
    borderWidth: StyleSheet.hairlineWidth,
    opacity: 0.6,
  },
  quickReplies: { gap: spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  inputBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
  },
  input: {
    flex: 1,
    maxHeight: 120,
    minHeight: 44,
    borderRadius: 22,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: spacing.lg,
    paddingTop: 12,
    paddingBottom: 12,
    fontSize: 15,
    fontFamily: fonts.regular,
  },
  send: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
});
