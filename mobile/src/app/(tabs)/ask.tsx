import { Ionicons } from '@expo/vector-icons';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { useChat, useReport, useSendMessage } from '@/api/hooks';
import { MessageBubble, Thinking } from '@/components/chat';
import { QueryState } from '@/components/Screen';
import { Chip } from '@/components/ui';
import { radius, spacing, useColors } from '@/theme';

const MAX_LENGTH = 500;

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

  const finding = report.data?.findings.find((f) => f.id === findingId);
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
      style={{ flex: 1 }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
    >
      {finding && (
        <View style={[styles.context, { backgroundColor: colors.accentSoft }]}>
          <Ionicons name="pricetag-outline" size={14} color={colors.accent} />
          <Text style={[styles.contextText, { color: colors.accent }]} numberOfLines={1}>
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
        </View>
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
                <Text style={[styles.emptyTitle, { color: colors.text }]}>Ask about your data</Text>
                <Text style={[styles.emptyText, { color: colors.muted }]}>
                  Answers come from computations on your own Fitbit data, and each one shows what
                  it is based on. I describe patterns; I don&apos;t give medical advice.
                </Text>
                <View style={styles.suggestions}>
                  {(finding ? [`Why did this happen?`, ...SUGGESTIONS] : SUGGESTIONS).map((text) => (
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
                  />
                ))}
                {pendingText && (
                  <>
                    <View style={[styles.pendingMine, { backgroundColor: colors.accent }]}>
                      <Text style={{ color: colors.onAccent, fontSize: 15 }}>{pendingText}</Text>
                    </View>
                    <Thinking />
                  </>
                )}
              </>
            )
          }
        </QueryState>
        {send.error && (
          <Text style={[styles.error, { color: colors.down }]}>
            Could not send your message. Check your connection and try again.
          </Text>
        )}
      </ScrollView>

      <View style={[styles.inputBar, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <TextInput
          value={draft}
          onChangeText={setDraft}
          placeholder="Ask about your sleep, activity, heart…"
          placeholderTextColor={colors.muted}
          maxLength={MAX_LENGTH}
          multiline
          style={[styles.input, { color: colors.text, backgroundColor: colors.background }]}
          accessibilityLabel="Message"
        />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Send"
          disabled={!canSend}
          onPress={() => submit(draft)}
          style={[styles.send, { backgroundColor: canSend ? colors.accent : colors.border }]}
        >
          <Ionicons name="arrow-up" size={20} color={canSend ? colors.onAccent : colors.muted} />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  context: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  contextText: { flex: 1, fontSize: 13, fontWeight: '600' },
  messages: {
    padding: spacing.lg,
    gap: spacing.md,
    flexGrow: 1,
    maxWidth: 720,
    width: '100%',
    alignSelf: 'center',
  },
  empty: { flex: 1, justifyContent: 'center', gap: spacing.md, paddingVertical: spacing.xl },
  emptyTitle: { fontSize: 22, fontWeight: '700' },
  emptyText: { fontSize: 15, lineHeight: 21 },
  suggestions: { gap: spacing.sm, alignItems: 'flex-start' },
  pendingMine: {
    alignSelf: 'flex-end',
    maxWidth: '85%',
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderRadius: radius.lg,
    borderBottomRightRadius: 4,
    opacity: 0.7,
  },
  error: { fontSize: 13, textAlign: 'center' },
  inputBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: spacing.sm,
    padding: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  input: {
    flex: 1,
    maxHeight: 120,
    minHeight: 40,
    borderRadius: 20,
    paddingHorizontal: spacing.md,
    paddingTop: 10,
    paddingBottom: 10,
    fontSize: 15,
  },
  send: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
});
