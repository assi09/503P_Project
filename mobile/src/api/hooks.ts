import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from './index';
import type { ReminderStatus } from './types';

export const keys = {
  report: ['report', 'latest'] as const,
  chat: ['chat'] as const,
  reminders: ['reminders'] as const,
  dataStatus: ['data-status'] as const,
};

export function useReport() {
  return useQuery({ queryKey: keys.report, queryFn: api.getLatestReport });
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
    mutationFn: ({ text, findingId }: { text: string; findingId?: string }) =>
      api.sendMessage(text, findingId),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.chat }),
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

export function useDataStatus() {
  return useQuery({ queryKey: keys.dataStatus, queryFn: api.getDataStatus });
}
