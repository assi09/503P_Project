import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';

import { useConversations, useDeleteConversation } from '@/api/hooks';
import type { Conversation } from '@/api/types';
import { Skeleton } from '@/components/Skeleton';
import { Text } from '@/components/Text';
import { timeAgo } from '@/lib/format';
import { isHovered } from '@/lib/platform';
import { fonts, radius, spacing, useColors } from '@/theme';

/**
 * The person's chats, newest first, with "New chat" on top. Every chat shares the same memory,
 * so the list only organises conversations; deleting one keeps what was learned in it.
 */
export function ConversationList({
  current,
  onSelect,
  onNew,
  newOpen,
}: {
  current?: string; // the open conversation's id
  onSelect: (id: string) => void;
  onNew: () => void;
  newOpen: boolean; // a new, still empty chat is open
}) {
  const colors = useColors();
  const list = useConversations();
  return (
    <View style={styles.list}>
      <Pressable
        accessibilityRole="button"
        onPress={onNew}
        style={(state) => [
          styles.newChat,
          { borderColor: colors.border },
          (isHovered(state) || newOpen) && { backgroundColor: colors.track },
        ]}
      >
        <Ionicons name="create-outline" size={18} color={colors.text} />
        <Text style={{ fontFamily: fonts.semibold }}>New chat</Text>
      </Pressable>
      <Text variant="label" color="muted" style={styles.heading}>
        Chats
      </Text>
      <ScrollView contentContainerStyle={{ gap: 2 }} showsVerticalScrollIndicator={false}>
        {list.isPending ? (
          [0, 1, 2].map((i) => <Skeleton key={i} height={40} radius={radius.sm} />)
        ) : list.error ? (
          <Pressable onPress={() => list.refetch()} style={styles.note}>
            <Text variant="caption" color="muted">
              Could not load your chats. Tap to try again.
            </Text>
          </Pressable>
        ) : list.data?.length ? (
          list.data.map((conversation) => (
            <ConversationRow
              key={conversation.id}
              conversation={conversation}
              selected={!newOpen && conversation.id === current}
              onSelect={() => onSelect(conversation.id)}
            />
          ))
        ) : (
          <Text variant="caption" color="muted" style={styles.note}>
            Your chats will appear here.
          </Text>
        )}
      </ScrollView>
      <Text variant="caption" color="faint" style={styles.shared}>
        Every chat shares what Patterns has learned about you.
      </Text>
    </View>
  );
}

function ConversationRow({
  conversation,
  selected,
  onSelect,
}: {
  conversation: Conversation;
  selected: boolean;
  onSelect: () => void;
}) {
  const colors = useColors();
  const remove = useDeleteConversation();
  const [confirming, setConfirming] = useState(false);
  const [hovered, setHovered] = useState(false);

  if (confirming) {
    return (
      <View style={[styles.row, { backgroundColor: colors.track }]}>
        <Text variant="caption" style={{ flex: 1 }} numberOfLines={1}>
          Delete this chat?
        </Text>
        <Pressable
          accessibilityRole="button"
          onPress={() => remove.mutate(conversation.id)}
          disabled={remove.isPending}
          hitSlop={6}
        >
          <Text variant="caption" color="danger" style={{ fontFamily: fonts.semibold }}>
            Delete
          </Text>
        </Pressable>
        <Pressable accessibilityRole="button" onPress={() => setConfirming(false)} hitSlop={6}>
          <Text variant="caption" color="muted" style={{ fontFamily: fonts.semibold }}>
            Keep
          </Text>
        </Pressable>
      </View>
    );
  }
  // The row and its delete button are siblings: a button inside a button is invalid on the web.
  return (
    <Pressable
      onHoverIn={() => setHovered(true)}
      onHoverOut={() => setHovered(false)}
      style={[styles.row, (selected || hovered) && { backgroundColor: colors.track }]}
    >
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ selected }}
        onPress={onSelect}
        onLongPress={() => setConfirming(true)} // phones have no hover to show the delete button
        style={styles.rowMain}
      >
        <Text numberOfLines={1} style={selected ? { fontFamily: fonts.semibold } : undefined}>
          {conversation.title}
        </Text>
        <Text variant="caption" color="muted" numberOfLines={1}>
          {timeAgo(conversation.updatedAt)}
        </Text>
      </Pressable>
      {(hovered || selected) && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Delete ${conversation.title}`}
          onPress={() => setConfirming(true)}
          hitSlop={8}
        >
          <Ionicons name="trash-outline" size={16} color={colors.muted} />
        </Pressable>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  list: { flex: 1, gap: spacing.sm },
  newChat: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
  },
  heading: { marginTop: spacing.md, paddingHorizontal: spacing.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
    borderRadius: radius.sm,
    minHeight: 48,
  },
  rowMain: { flex: 1, gap: 1 },
  note: { paddingHorizontal: spacing.sm, paddingVertical: spacing.sm },
  shared: { paddingHorizontal: spacing.sm },
});
