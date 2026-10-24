import { editLog } from '@/lib/actionLog';

import { httpClient } from '../http';
import { DEMO_OWNER, mockClient } from '../mock';
import { saveToken } from '../token';
import type { HealthLog } from '../types';

const FOOD: HealthLog = {
  kind: 'food', foodName: 'Example meal', mealType: 'LUNCH',
  consumedAt: '2026-10-24T12:00:00+03:00', proteinG: 40, provenance: 'user_entered',
};

beforeEach(async () => {
  const { token } = await mockClient.logIn(DEMO_OWNER);
  await saveToken(token);
});
afterEach(async () => { await saveToken(null); });

it('keeps absent quantities unknown and preserves an explicit zero', () => {
  expect(editLog(FOOD, { proteinG: '0', fatG: '' })).toMatchObject({ proteinG: 0 });
  expect(editLog(FOOD, { fatG: '' })).not.toHaveProperty('fatG');
  expect(() => editLog(FOOD, { proteinG: 'NaN' })).toThrow();
  expect(() => editLog(FOOD, { consumedAt: '2026-10-24T12:00:00' })).toThrow('timezone');
});

it('revises the reviewed version, blocks stale confirmation and supports confirmed undo', async () => {
  const draft = await mockClient.proposeAction('lifecycle', FOOD);
  const changed = await mockClient.reviseAction(draft.id, 1, { ...FOOD, proteinG: 45 });
  expect(changed.version).toBe(2);
  await expect(mockClient.confirmAction(draft.id, 1)).rejects.toMatchObject({ code: 'stale_action' });
  await expect(mockClient.confirmAction(draft.id, 2)).resolves.toMatchObject({ status: 'succeeded' });
  await expect(mockClient.confirmAction(draft.id, 2)).resolves.toMatchObject({ status: 'succeeded' });
  await expect(mockClient.undoAction(draft.id, 2)).resolves.toMatchObject({ status: 'undone' });
});

it('prevents duplicate drafts and keeps cancellation from becoming a log', async () => {
  const log = { ...FOOD, foodName: 'Another example meal' };
  const draft = await mockClient.proposeAction('duplicate', log);
  await expect(mockClient.proposeAction('duplicate', log)).resolves.toMatchObject({ id: draft.id });
  await expect(mockClient.proposeAction('another-key', log)).rejects.toMatchObject({ code: 'duplicate_log' });
  await mockClient.cancelAction(draft.id, 1);
  await expect(mockClient.confirmAction(draft.id, 1)).rejects.toMatchObject({ code: 'stale_action' });
});

it('does not expose another account’s drafts', async () => {
  const draft = await mockClient.proposeAction('ownership', { ...FOOD, foodName: 'Private demo meal' });
  const person = await mockClient.signUp({ email: 'action-person@example.com', password: 'long enough password' });
  const request = (await mockClient.getAccessRequests()).find((r) => r.email === 'action-person@example.com')!;
  await mockClient.decideAccessRequest(request.id, true);
  await saveToken(person.token);
  await expect(mockClient.getAction(draft.id)).rejects.toMatchObject({ status: 404 });
});

it('uses versioned backend operations without silently falling back to demo writes', async () => {
  const original = globalThis.fetch;
  const fetch = jest.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ error: { code: 'write_scope_needed', message: 'Allow logging first.' } }) });
  globalThis.fetch = fetch;
  try {
    const client = httpClient('http://api.test', mockClient);
    await expect(client.confirmAction('a b', 3)).rejects.toMatchObject({ code: 'write_scope_needed' });
    expect(fetch.mock.calls[0][0]).toBe('http://api.test/actions/a%20b/confirm');
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ version: 3 });
    await expect(client.connectGoogle('food_logging')).rejects.toMatchObject({ status: 403 });
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ capability: 'food_logging' });
  } finally { globalThis.fetch = original; }
});
