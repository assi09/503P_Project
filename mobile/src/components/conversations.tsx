import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import { Platform, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';

import { useConversations, useDeleteConversation, useUpdateConversation } from '@/api/hooks';
import type { Conversation } from '@/api/types';
import { Skeleton } from '@/components/Skeleton';
import { Text } from '@/components/Text';
import { timeAgo } from '@/lib/format';
import { isHovered } from '@/lib/platform';
import { fonts, radius, spacing, useColors } from '@/theme';

type IconName = keyof typeof Ionicons.glyphMap;

/**
 * The person's chats, pinned ones first, with "New chat" on top. Every chat shares the same
 * memory, so the list only organises conversations; deleting one keeps what was learned in it.
 */
export function ConversationList({
  current,
  onSelect,
  onNew,
  newOpen,
  onCollapse,
}: {
  current?: string; // the open conversation's id
  onSelect: (id: string) => void;
  onNew: () => void;
  newOpen: boolean; // a new, still empty chat is open
  onCollapse?: () => void; // the sidebar can be hidden: wide screens
}) {
  const colors = useColors();
  const list = useConversations();
  const pinned = list.data?.filter((c) => c.pinned) ?? [];
  const recent = list.data?.filter((c) => !c.pinned) ?? [];
  const rows = (conversations: Conversation[]) =>
    conversations.map((conversation) => (
      <ConversationRow
        key={conversation.id}
        conversation={conversation}
        selected={!newOpen && conversation.id === current}
        onSelect={() => onSelect(conversation.id)}
        // The sidebar shows the menu button on hover; the phone's page has no hover to wait for.
        showMenu={!onCollapse}
      />
    ));

  return (
    <View style={styles.list}>
      <View style={styles.top}>
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
        {onCollapse && (
          <IconButton icon="chevron-back" label="Hide your chats" onPress={onCollapse} />
        )}
      </View>
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
          <>
            {pinned.length > 0 && (
              <Text variant="label" color="muted" style={styles.heading}>
                Pinned
              </Text>
            )}
            {rows(pinned)}
            {recent.length > 0 && (
              <Text variant="label" color="muted" style={styles.heading}>
                Recent
              </Text>
            )}
            {rows(recent)}
          </>
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

/** A small round icon button, e.g. to hide or show the list of chats. */
export function IconButton({
  icon,
  label,
  onPress,
  size = 18,
}: {
  icon: IconName;
  label: string;
  onPress: () => void;
  size?: number;
}) {
  const colors = useColors();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      hitSlop={6}
      style={(state) => [
        styles.iconButton,
        (isHovered(state) || state.pressed) && { backgroundColor: colors.track },
      ]}
    >
      <Ionicons name={icon} size={size} color={colors.muted} />
    </Pressable>
  );
}

type Mode = 'idle' | 'menu' | 'rename' | 'delete';

function ConversationRow({
  conversation,
  selected,
  onSelect,
  showMenu,
}: {
  conversation: Conversation;
  selected: boolean;
  onSelect: () => void;
  showMenu: boolean; // always show the menu button, not only on hover
}) {
  const colors = useColors();
  const update = useUpdateConversation();
  const remove = useDeleteConversation();
  const [mode, setMode] = useState<Mode>('idle');
  const [hovered, setHovered] = useState(false);
  const [title, setTitle] = useState(conversation.title);

  function saveTitle() {
    const trimmed = title.trim();
    if (trimmed && trimmed !== conversation.title) {
      update.mutate({ id: conversation.id, changes: { title: trimmed } });
    }
    setMode('idle');
  }

  if (mode === 'rename') {
    return (
      <View style={[styles.row, { backgroundColor: colors.track }]}>
        <TextInput
          accessibilityLabel="Chat name"
          value={title}
          onChangeText={setTitle}
          autoFocus
          maxLength={120}
          onSubmitEditing={saveTitle}
          onKeyPress={(event) => {
            if (Platform.OS === 'web' && event.nativeEvent.key === 'Escape') setMode('idle');
          }}
          selectTextOnFocus
          style={[
            styles.input,
            { color: colors.text, borderColor: colors.border, backgroundColor: colors.surface },
          ]}
        />
        <IconButton icon="checkmark" label="Save the name" onPress={saveTitle} size={16} />
        <IconButton icon="close" label="Keep the name" onPress={() => setMode('idle')} size={16} />
      </View>
    );
  }
  if (mode === 'delete') {
    return (
      <View style={[styles.row, { backgroundColor: colors.track }]}>
        <Text variant="caption" style={{ flex: 1 }} numberOfLines={2}>
          Delete this chat? What Patterns learned stays.
        </Text>
        <TextAction label="Delete" danger onPress={() => remove.mutate(conversation.id)} />
        <TextAction label="Keep" onPress={() => setMode('idle')} />
      </View>
    );
  }

  const highlighted = selected || hovered || mode === 'menu';
  return (
    <View>
      {/* The row and its menu button are siblings: a button inside a button is invalid on the web. */}
      <Pressable
        onHoverIn={() => setHovered(true)}
        onHoverOut={() => setHovered(false)}
        style={[styles.row, highlighted && { backgroundColor: colors.track }]}
      >
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ selected }}
          onPress={onSelect}
          onLongPress={() => setMode('menu')}
          style={styles.rowMain}
        >
          <Text numberOfLines={1} style={selected ? { fontFamily: fonts.semibold } : undefined}>
            {conversation.title}
          </Text>
          <Text variant="caption" color="muted" numberOfLines={1}>
            {timeAgo(conversation.updatedAt)}
          </Text>
        </Pressable>
        {(highlighted || showMenu || Platform.OS !== 'web') && (
          <IconButton
            icon="ellipsis-horizontal"
            label={`Options for ${conversation.title}`}
            onPress={() => setMode(mode === 'menu' ? 'idle' : 'menu')}
            size={16}
          />
        )}
      </Pressable>
      {mode === 'menu' && (
        <View
          accessibilityRole="menu"
          style={[styles.menu, { borderColor: colors.border, backgroundColor: colors.surface }]}
        >
          <MenuItem
            icon={conversation.pinned ? 'pin' : 'pin-outline'}
            label={conversation.pinned ? 'Unpin' : 'Pin'}
            onPress={() => {
              update.mutate({ id: conversation.id, changes: { pinned: !conversation.pinned } });
              setMode('idle');
            }}
          />
          <MenuItem
            icon="pencil-outline"
            label="Rename"
            onPress={() => {
              setTitle(conversation.title);
              setMode('rename');
            }}
          />
          <MenuItem icon="trash-outline" label="Delete" danger onPress={() => setMode('delete')} />
        </View>
      )}
    </View>
  );
}

function MenuItem({
  icon,
  label,
  onPress,
  danger = false,
}: {
  icon: IconName;
  label: string;
  onPress: () => void;
  danger?: boolean;
}) {
  const colors = useColors();
  const color = danger ? colors.danger : colors.text;
  return (
    <Pressable
      accessibilityRole="menuitem"
      onPress={onPress}
      style={(state) => [
        styles.menuItem,
        (isHovered(state) || state.pressed) && { backgroundColor: colors.track },
      ]}
    >
      <Ionicons name={icon} size={16} color={color} />
      <Text style={{ color }}>{label}</Text>
    </Pressable>
  );
}

function TextAction({
  label,
  onPress,
  danger = false,
}: {
  label: string;
  onPress: () => void;
  danger?: boolean;
}) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} hitSlop={6}>
      <Text
        variant="caption"
        color={danger ? 'danger' : 'muted'}
        style={{ fontFamily: fonts.semibold }}
      >
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  list: { flex: 1, gap: spacing.sm },
  top: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  newChat: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
  },
  iconButton: {
    width: 32,
    height: 32,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  heading: { marginTop: spacing.md, marginBottom: 2, paddingHorizontal: spacing.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingLeft: spacing.sm,
    paddingRight: 4,
    paddingVertical: spacing.sm,
    borderRadius: radius.sm,
    minHeight: 48,
  },
  rowMain: { flex: 1, gap: 1 },
  input: {
    flex: 1,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    fontFamily: fonts.regular,
    fontSize: 15,
  },
  menu: {
    marginTop: 2,
    marginBottom: spacing.xs,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radius.md,
    padding: 4,
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 8,
    borderRadius: radius.sm,
  },
  note: { paddingHorizontal: spacing.sm, paddingVertical: spacing.sm },
  shared: { paddingHorizontal: spacing.sm },
});
