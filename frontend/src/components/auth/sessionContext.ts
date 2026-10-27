import { createContext, useContext } from 'react';
import type { AuthSession, User } from '../../api/auth.types';

export type SignedInSession = Omit<AuthSession, 'user'> & { user: User };
export const SessionContext = createContext<{ session: SignedInSession; logout: () => Promise<void> } | null>(null);
export function useSession() {
  const value = useContext(SessionContext);
  if (!value) throw new Error('账号上下文尚未就绪。');
  return value;
}
