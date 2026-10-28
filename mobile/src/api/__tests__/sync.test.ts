import { QueryClient } from '@tanstack/react-query';

import { keys, refreshSyncedData, requestSync } from '../hooks';
import { api } from '../index';
import type { GoogleStatus } from '../types';

const ACTIVE: GoogleStatus = {
  status: 'active',
  syncing: false,
  lastSync: null,
  lastError: null,
  missingScopes: [],
};

const clients: QueryClient[] = [];

function clientWith(status: GoogleStatus): QueryClient {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(client);
  client.setQueryData(keys.google, status);
  return client;
}

describe('syncing without a button', () => {
  afterEach(() => {
    jest.restoreAllMocks();
    clients.splice(0).forEach((client) => client.clear()); // no cache timers left behind
  });

  it('asks the server to sync when Google is connected, and keeps its answer', async () => {
    const answer = { ...ACTIVE, syncing: true };
    const sync = jest.spyOn(api, 'syncGoogle').mockResolvedValue(answer);
    const client = clientWith(ACTIVE);
    await requestSync(client);
    expect(sync).toHaveBeenCalledWith(); // never forced: the server decides if one is due
    expect(client.getQueryData(keys.google)).toEqual(answer);
  });

  it.each<[string, GoogleStatus]>([
    ['not connected', { ...ACTIVE, status: 'none' }],
    ['sign-in expired', { ...ACTIVE, status: 'reconnect_needed' }],
    ['already syncing', { ...ACTIVE, syncing: true }],
  ])('does nothing when %s', async (_, status) => {
    const sync = jest.spyOn(api, 'syncGoogle');
    await requestSync(clientWith(status));
    expect(sync).not.toHaveBeenCalled();
  });

  it('stays quiet when the server refuses or the network is down', async () => {
    jest.spyOn(api, 'syncGoogle').mockRejectedValue(new Error('offline'));
    await expect(requestSync(clientWith(ACTIVE))).resolves.toBeUndefined();
  });

  it('reloads what a finished sync can change, and nothing else', async () => {
    const client = clientWith(ACTIVE);
    const invalidate = jest.spyOn(client, 'invalidateQueries');
    await refreshSyncedData(client);
    const refreshed = invalidate.mock.calls.map(([filters]) => filters?.queryKey?.[0]);
    expect(refreshed).toEqual(expect.arrayContaining(['day', 'workouts', 'metric', 'report']));
    expect(refreshed).not.toContain('chat');
  });
});
