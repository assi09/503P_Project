import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiError } from './http';
import { api } from './index';
import type { ChatMessage, NotificationSettings, ReminderStatus, SendOptions } from './types';

export const keys = {
  report: ['report', 'latest'] as const,
  chat: ['chat'] as const,
  reminders: ['reminders'] as const,
  dataStatus: ['data-status'] as const,
  notificationSettings: ['settings', 'notifications'] as const,
  accessRequests: ['admin', 'access-requests'] as const,
  google: ['google', 'status'] as const,
};

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

export function useChat() {
  return useQuery({
    queryKey: keys.chat,
    queryFn: api.getChat,
    // A question without an answer yet is still being answered on the server: check back.
    refetchInterval: (query) => (query.state.data?.at(-1)?.role === 'user' ? 4000 : false),
  });
}

export function useSendMessage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ text, options }: { text: string; options: SendOptions }) =>
      api.sendMessage(text, options),
    // Append directly so the conversation never flickers while it refetches.
    onSuccess: (added) =>
      client.setQueryData<ChatMessage[]>(keys.chat, (old = []) => [...old, ...added]),
    // A slow answer was still stored with its question: reload to show them as they arrive.
    onError: (error) => {
      if (error instanceof ApiError && error.code === 'still_answering') {
        client.invalidateQueries({ queryKey: keys.chat });
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
