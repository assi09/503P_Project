import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from './index';
import type { ChatMessage, NotificationSettings, ReminderStatus, SendOptions } from './types';

export const keys = {
  report: ['report', 'latest'] as const,
  chat: ['chat'] as const,
  reminders: ['reminders'] as const,
  dataStatus: ['data-status'] as const,
  notificationSettings: ['settings', 'notifications'] as const,
  accessRequests: ['admin', 'access-requests'] as const,
};

export function useReport() {
  return useQuery({ queryKey: keys.report, queryFn: api.getLatestReport });
}

export function useEvidence(id: string) {
  return useQuery({ queryKey: ['evidence', id], queryFn: () => api.getEvidence(id) });
}

export function useAnswerQuestion() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, answer }: { id: string; answer: string }) => api.answerQuestion(id, answer),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.report }),
  });
}

export function useChat() {
  return useQuery({ queryKey: keys.chat, queryFn: api.getChat });
}

export function useSendMessage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ text, options }: { text: string; options: SendOptions }) =>
      api.sendMessage(text, options),
    // Append directly so the conversation never flickers while it refetches.
    onSuccess: (added) =>
      client.setQueryData<ChatMessage[]>(keys.chat, (old = []) => [...old, ...added]),
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
