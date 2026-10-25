import { Ionicons } from '@expo/vector-icons';
import { router, useLocalSearchParams } from 'expo-router';
import { BottomTabBarHeightContext } from 'expo-router/js-tabs';
import { useContext, useEffect, useMemo, useRef, useState } from 'react';
import {
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  View,
  type ScrollViewInstance,
} from 'react-native';
import Animated, { FadeIn, FadeOut, LinearTransition } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useChat, useReport, useSendMessage } from '@/api/hooks';
import type { Attachment, Depth, ExpertChoice, Finding } from '@/api/types';
import { AttachSheet } from '@/components/attach';
import { MessageBubble, Thinking } from '@/components/chat';
import { Composer } from '@/components/composer';
import { QueryState } from '@/components/Screen';
import { Text } from '@/components/Text';
import { Chip } from '@/components/ui';
import { expertInfo, useExpertColor } from '@/lib/experts';
import { metricLabel } from '@/lib/format';
import { DURATION, EASE_OUT } from '@/lib/motion';
import { floatingTabBar } from '@/lib/platform';
import { column, radius, spacing, useColors } from '@/theme';

const MAX_LENGTH = 500;

// The composer moves from the middle of the empty page down to the bottom of the conversation.
const MOVE = LinearTransition.duration(DURATION.normal).easing(EASE_OUT);

// Questions offered while a finding is attached.
const FINDING_SUGGESTIONS = ['Why did this happen?', 'What else changed around then?'];

function attachmentLabel(attachment: Attachment | undefined, findings: Finding[]): string | undefined {
  if (!attachment) return undefined;
  if (attachment.kind === 'metric') return metricLabel(attachment.metric);
  return findings.find((f) => f.id === attachment.id)?.title ?? 'A finding';
}

export default function AskScreen() {
  const colors = useColors();
  const { findingId, metric } = useLocalSearchParams<{ findingId?: string; metric?: string }>();
  const chat = useChat();
  const report = useReport();
  const send = useSendMessage();
  const [draft, setDraft] = useState('');
  const [expert, setExpert] = useState<ExpertChoice>('auto');
  const [depth, setDepth] = useState<Depth>('quick');
  const [attachment, setAttachment] = useState<Attachment>();
  const [attaching, setAttaching] = useState(false);
  const scroll = useRef<ScrollViewInstance>(null);
  const insets = useSafeAreaInsets();
  const barHeight = useContext(BottomTabBarHeightContext) ?? 0;
  const tabBarHeight = floatingTabBar ? barHeight : 0;
  const keyboardOpen = useKeyboardOpen();

  // "Ask about this" on a finding opens this tab with the finding attached. The parameter is then
  // cleared, so asking about the same finding again attaches it again.
  // A metric page's "Ask about" works the same way with the metric.
  const [seenFindingId, setSeenFindingId] = useState<string>();
  if (findingId !== seenFindingId) {
    setSeenFindingId(findingId);
    if (findingId) setAttachment({ kind: 'finding', id: findingId });
  }
  const [seenMetric, setSeenMetric] = useState<string>();
  if (metric !== seenMetric) {
    setSeenMetric(metric);
    if (metric) setAttachment({ kind: 'metric', metric });
  }
  useEffect(() => {
    if (findingId) router.setParams({ findingId: undefined });
  }, [findingId]);
  useEffect(() => {
    if (metric) router.setParams({ metric: undefined });
  }, [metric]);

  // Once a slow answer shows up in the chat, its "taking longer" message has done its job.
  const lastRole = chat.data?.at(-1)?.role;
  const { reset: resetSend } = send;
  const slow = (send.error as { code?: string } | null)?.code === 'still_answering';
  useEffect(() => {
    if (slow && lastRole === 'assistant') resetSend();
  }, [slow, lastRole, resetSend]);

  const findings = useMemo(() => report.data?.findings ?? [], [report.data]);
  const findingTitles = useMemo(
    () => Object.fromEntries(findings.map((f) => [f.id, f.title])),
    [findings],
  );
  const messages = chat.data ?? [];
  const pendingText = send.isPending ? send.variables?.text : undefined;
  const pendingExpert = send.variables?.options.expert ?? expert;
  const started = messages.length > 0 || pendingText !== undefined;
  const sendError = send.error && (
    <Text variant="caption" color="danger" style={{ textAlign: 'center' }}>
      {send.error.message || 'Could not send your message.'}
      {/* A slow answer is still coming; other errors can be retried. */}
      {slow ? '' : ' Try again.'}
    </Text>
  );

  useEffect(() => {
    scroll.current?.scrollToEnd({ animated: true });
  }, [messages.length, send.isPending]);

  function submit(text: string) {
    const trimmed = text.trim();
    if (!trimmed || send.isPending) return;
    send.mutate(
      { text: trimmed, options: { expert, depth, ...(attachment && { attachment }) } },
      {
        // Keep the text if sending fails, so it can be retried.
        onSuccess: () => {
          setDraft('');
          setAttachment(undefined);
        },
      },
    );
  }

  const suggestions =
    attachment?.kind === 'finding'
      ? FINDING_SUGGESTIONS
      : expertInfo(expert).suggestions;

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.background }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Text variant={started ? 'headline' : 'display'} accessibilityRole="header">
          Ask
        </Text>
      </View>

      <QueryState query={chat}>
        {() =>
          started ? (
            <ScrollView
              ref={scroll}
              style={{ flex: 1 }}
              contentContainerStyle={styles.messages}
              keyboardShouldPersistTaps="handled"
            >
              {messages.map((message) => (
                <MessageBubble
                  key={message.id}
                  message={message}
                  knownEvidence={report.data?.evidence ?? {}}
                  findingTitles={findingTitles}
                />
              ))}
              {pendingText !== undefined && (
                <>
                  <View
                    style={[
                      styles.pendingMine,
                      { backgroundColor: colors.surfaceRaised, borderColor: colors.border },
                    ]}
                  >
                    <Text>{pendingText}</Text>
                  </View>
                  <Thinking expert={pendingExpert} />
                </>
              )}
              {sendError}
            </ScrollView>
          ) : (
            <Animated.View exiting={FadeOut.duration(150)} style={styles.greeting}>
              <Greeting expert={expert} />
              {/* The first question's error, e.g. no data yet, shows before any conversation. */}
              {sendError}
            </Animated.View>
          )
        }
      </QueryState>

      {started && attachment?.kind === 'finding' && (
        <ScrollView
          horizontal
          style={styles.quickRail}
          showsHorizontalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={styles.quickReplies}
        >
          {FINDING_SUGGESTIONS.map((text) => (
            <Chip key={text} label={text} disabled={send.isPending} onPress={() => submit(text)} />
          ))}
        </ScrollView>
      )}

      <Animated.View
        layout={MOVE}
        style={[
          styles.composer,
          // Above the floating tab bar, except while the keyboard covers it.
          { paddingBottom: started ? (keyboardOpen ? 0 : tabBarHeight) + spacing.sm : spacing.md },
        ]}
      >
        <Composer
          value={draft}
          onChangeText={setDraft}
          onSubmit={() => submit(draft)}
          expert={expert}
          onExpertChange={setExpert}
          depth={depth}
          onDepthChange={setDepth}
          attachmentLabel={attachmentLabel(attachment, findings)}
          onAttach={() => setAttaching(true)}
          onClearAttachment={() => setAttachment(undefined)}
          busy={send.isPending}
          collapsible={!started}
          placeholder={started ? 'Ask a follow-up' : 'Ask about your sleep, recovery, activity…'}
          maxLength={MAX_LENGTH}
        />
      </Animated.View>

      {!started && (
        <Animated.View exiting={FadeOut.duration(150)} style={styles.below}>
          <View style={styles.suggestions}>
            {suggestions.map((text, i) => (
              <Animated.View key={`${expert}-${text}`} entering={FadeIn.delay(i * 40).duration(DURATION.fast)}>
                <Chip label={text} onPress={() => submit(text)} />
              </Animated.View>
            ))}
          </View>
        </Animated.View>
      )}

      <AttachSheet
        visible={attaching}
        findings={findings}
        onClose={() => setAttaching(false)}
        onPick={(picked) => {
          setAttachment(picked);
          setAttaching(false);
        }}
      />
    </KeyboardAvoidingView>
  );
}

/** The empty page: the selected expert's icon, a question, and what the answers are based on. */
function Greeting({ expert }: { expert: ExpertChoice }) {
  const color = useExpertColor(expert);
  const info = expertInfo(expert);
  return (
    <>
      <Animated.View
        key={expert}
        entering={FadeIn.duration(250)}
        style={[styles.greetingIcon, { backgroundColor: `${color}22`, borderColor: `${color}44` }]}
      >
        <Ionicons name={info.icon} size={24} color={color} />
      </Animated.View>
      <Text variant="title" style={{ textAlign: 'center' }}>
        {expert === 'auto' ? 'What do you want to know?' : `Ask the ${info.label} expert`}
      </Text>
      <Text color="muted" style={styles.disclaimer}>
        Answers come from your own Fitbit data and show what they are based on. Patterns, not
        medical advice.
      </Text>
    </>
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
  header: { ...column, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  greeting: {
    ...column,
    flex: 1,
    justifyContent: 'flex-end',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.xl,
  },
  greetingIcon: {
    width: 56,
    height: 56,
    borderRadius: 28,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.sm,
  },
  disclaimer: { textAlign: 'center', maxWidth: 340 },
  below: { ...column, flex: 1, paddingHorizontal: spacing.lg },
  suggestions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: spacing.sm,
  },
  messages: { ...column, padding: spacing.lg, gap: spacing.lg, flexGrow: 1 },
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
  quickRail: { ...column, flexGrow: 0 },
  quickReplies: { gap: spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  composer: { ...column, paddingHorizontal: spacing.md, paddingTop: spacing.sm },
});
