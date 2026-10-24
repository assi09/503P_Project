import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

interface Session {
  signedIn: boolean;
  signIn: () => void;
  signOut: () => void;
}

const SessionContext = createContext<Session | null>(null);

// Placeholder until accounts exist: "signing in" only leaves the landing page, and is forgotten
// on reload. The routes already switch on `signedIn`, so real auth only has to replace this.
export function SessionProvider({ children }: { children: ReactNode }) {
  const [signedIn, setSignedIn] = useState(false);
  const value = useMemo(
    () => ({
      signedIn,
      signIn: () => setSignedIn(true),
      signOut: () => setSignedIn(false),
    }),
    [signedIn],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error('useSession must be used inside SessionProvider');
  return session;
}
