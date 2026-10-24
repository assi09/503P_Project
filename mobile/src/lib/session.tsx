import { useQueryClient } from '@tanstack/react-query';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { api } from '@/api';
import { ApiError } from '@/api/http';
import { loadToken, saveToken } from '@/api/token';
import type { Account, Credentials, SignedIn } from '@/api/types';

type State =
  | { phase: 'loading' } // reading the stored token at launch
  | { phase: 'signedOut' }
  | { phase: 'signedIn'; account: Account };

interface Session {
  state: State;
  account: Account | undefined;
  signUp: (credentials: Credentials) => Promise<void>;
  logIn: (credentials: Credentials) => Promise<void>;
  logOut: () => Promise<void>;
  refresh: () => Promise<void>; // re-reads the account, e.g. to see whether it was approved
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<State>({ phase: 'loading' });

  const signOutLocally = useCallback(async () => {
    await saveToken(null);
    queryClient.clear(); // nothing of one person's data stays for the next
    setState({ phase: 'signedOut' });
  }, [queryClient]);

  const refresh = useCallback(async () => {
    try {
      setState({ phase: 'signedIn', account: await api.getAccount() });
    } catch (error) {
      // An ended session signs out; a network failure keeps the token for the next try.
      if (error instanceof ApiError && error.status === 401) await signOutLocally();
      else setState((current) => (current.phase === 'loading' ? { phase: 'signedOut' } : current));
    }
  }, [signOutLocally]);

  useEffect(() => {
    loadToken().then((token) => (token ? refresh() : setState({ phase: 'signedOut' })));
  }, [refresh]);

  const value = useMemo<Session>(() => {
    const enter = async ({ token, account }: SignedIn) => {
      await saveToken(token);
      setState({ phase: 'signedIn', account });
    };
    return {
      state,
      account: state.phase === 'signedIn' ? state.account : undefined,
      signUp: async (credentials) => enter(await api.signUp(credentials)),
      logIn: async (credentials) => enter(await api.logIn(credentials)),
      logOut: async () => {
        await api.logOut().catch(() => undefined); // signing out locally is what matters
        await signOutLocally();
      },
      refresh,
    };
  }, [state, refresh, signOutLocally]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error('useSession must be used inside SessionProvider');
  return session;
}
