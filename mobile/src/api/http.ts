// Client for the real backend API. Endpoints are filled in as the backend implements them.
import type { ApiClient } from './types';

export function httpClient(baseUrl: string): ApiClient {
  const notYet = (endpoint: string) => () =>
    Promise.reject(new Error(`${endpoint} is not implemented by the backend yet (${baseUrl})`));

  return {
    getLatestReport: notYet('GET /reports/latest'),
    getEvidence: notYet('GET /evidence/{id}'),
    answerQuestion: notYet('POST /questions/{id}/answer'),
    getChat: notYet('GET /chat'),
    sendMessage: notYet('POST /chat'),
    getReminders: notYet('GET /reminders'),
    setReminderStatus: notYet('PATCH /reminders/{id}'),
    getNotificationSettings: notYet('GET /settings/notifications'),
    updateNotificationSettings: notYet('PUT /settings/notifications'),
    getDataStatus: notYet('GET /data/status'),
  };
}
