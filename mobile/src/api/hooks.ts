import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiError } from './http';
import { api } from './index';
import type {
  ChatMessage,
  ISODate,
  NotificationSettings,
  ReminderStatus,
  SendOptions,
} from './types';

export const keys = {
  report: ['report', 'latest'] as const,
  chat: ['chat'] as const,
  conversations: ['conversations'] as const,
  reminders: ['reminders'] as const,
  dataStatus: ['data-status'] as const,
  notificationSettings: ['settings', 'notifications'] as const,
  accessRequests: ['admin', 'access-requests'] as const,
  google: ['google', 'status'] as const,
};

/** A day's numbers; 'latest' is the newest day with data. Kept while moving between days. */
export function useDay(date: ISODate | 'latest') {
  return useQuery({
    queryKey: ['day', date],
    queryFn: () => api.getDay(date),
    placeholderData: (previous) => previous,
  });
}

export function useMetricSeries(metric: string, days: number, end?: ISODate) {
  return useQuery({
    queryKey: ['metric', metric, days, end ?? 'latest'],
    queryFn: () => api.getMetricSeries(metric, { end, days }),
    placeholderData: (previous) => previous,
  });
}

export function useReport() {
  return useQuery({ queryKey: keys.report, queryFn: api.getLatestReport });
}

export function useEvidence(id: string, enabled = true) {
  return useQuery({ queryKey: ['evidence', id], queryFn: () => api.getEvidence(id), enabled });
}

export function useAnswerQuestion() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, answer }: { id: string; answer: string }) => api.answerQuestion(id, answer),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.report }),
  });
}

/** Which chat is open: a conversation, the latest one, or a new one not created yet. */
export type ChatTarget = string | 'latest' | 'new';

export function useChat(target: ChatTarget = 'latest') {
  return useQuery({
    queryKey: [...keys.chat, target],
    queryFn: () => (target === 'new' ? [] : api.getChat(target === 'latest' ? undefined : target)),
    // A question without an answer yet is still being answered on the server: check back.
    refetchInterval: (query) => (query.state.data?.at(-1)?.role === 'user' ? 4000 : false),
  });
}

export function useConversations() {
  return useQuery({ queryKey: keys.conversations, queryFn: api.getConversations });
}

export function useUpdateConversation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: { title?: string; pinned?: boolean } }) =>
      api.updateConversation(id, changes),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.conversations }),
  });
}

export function useDeleteConversation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteConversation(id),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.conversations });
      client.invalidateQueries({ queryKey: keys.chat });
    },
  });
}

/** Sends to the open chat; a new chat is created on its first message, so none are left empty. */
export function useSendMessage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({
      text,
      options,
      target,
    }: {
      text: string;
      options: SendOptions;
      target: ChatTarget;
    }) => {
      const conversationId =
        target === 'new'
          ? (await api.createConversation()).id
          : target === 'latest'
            ? undefined
            : target;
      return api.sendMessage(text, { ...options, conversationId });
    },
    // Append directly so the conversation never flickers while it refetches.
    onSuccess: (added, { target, options }) => {
      const id = added[0]?.conversationId;
      // An edited or retried question replaced itself and everything after it.
      const append = (old: ChatMessage[] = []) => {
        const cut = options.replaces ? old.findIndex((m) => m.id === options.replaces) : -1;
        return [...(cut >= 0 ? old.slice(0, cut) : old), ...added];
      };
      if (id) client.setQueryData<ChatMessage[]>([...keys.chat, id], append);
      if (target === 'latest') client.setQueryData<ChatMessage[]>([...keys.chat, 'latest'], append);
      client.invalidateQueries({ queryKey: keys.conversations });
    },
    // A slow answer was still stored with its question: reload to show them as they arrive.
    onError: (error) => {
      if (error instanceof ApiError && error.code === 'still_answering') {
        client.invalidateQueries({ queryKey: keys.chat });
        client.invalidateQueries({ queryKey: keys.conversations });
      }
    },
  });
}

export function useReminders() {
  return useQuery({ queryKey: keys.reminders, queryFn: api.getReminders });
}

export function useSetReminderStatus() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: ReminderStatus }) =>
      api.setReminderStatus(id, status),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.reminders }),
  });
}

export function useNotificationSettings() {
  return useQuery({ queryKey: keys.notificationSettings, queryFn: api.getNotificationSettings });
}

export function useUpdateNotificationSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (settings: NotificationSettings) => api.updateNotificationSettings(settings),
    onSuccess: (saved) => client.setQueryData(keys.notificationSettings, saved),
  });
}

export function useDataStatus() {
  return useQuery({ queryKey: keys.dataStatus, queryFn: api.getDataStatus });
}

export function useAccessRequests() {
  return useQuery({ queryKey: keys.accessRequests, queryFn: api.getAccessRequests });
}

export function useDecideAccessRequest() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, approve }: { id: string; approve: boolean }) =>
      api.decideAccessRequest(id, approve),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.accessRequests }),
  });
}

export function useGoogleStatus() {
  return useQuery({
    queryKey: keys.google,
    queryFn: api.getGoogleStatus,
    refetchInterval: (query) => (query.state.data?.syncing ? 3000 : false), // until it is done
  });
}

/** Sync now or disconnect; both answer with the new status. */
export function useGoogleAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (action: 'sync' | 'disconnect') =>
      action === 'sync' ? api.syncGoogle() : api.disconnectGoogle(),
    onSuccess: (status) => client.setQueryData(keys.google, status),
  });
}
