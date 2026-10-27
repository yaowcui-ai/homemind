import { lazy, Suspense, useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Alert, Button, ConfigProvider, Spin } from 'antd';
import { authApi } from '../../api/auth';
import { invalidateSession, subscribeUnauthorized } from '../../api/client';
import type { AuthSession } from '../../api/auth.types';
import { SessionContext } from './sessionContext';
import styles from './Auth.module.css';

const AuthForm = lazy(() => import('./AuthForm'));
const popupContainer = () => document.getElementById('homemind-session-surface') ?? document.body;
let bootstrap: Promise<AuthSession> | null = null;
function readSession(force = false) {
  if (force) bootstrap = null;
  if (!bootstrap) {
    const current = authApi.session().finally(() => { if (bootstrap === current) bootstrap = null; });
    bootstrap = current;
  }
  return bootstrap;
}

export default function AuthGate({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const [session, setSession] = useState<AuthSession | undefined>();
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [transitioning, setTransitioning] = useState(false);
  const generation = useRef(0);
  const accepted = useRef<AuthSession | undefined>(undefined);
  const accept = useCallback((value: AuthSession) => {
    if (!accepted.current || accepted.current.user?.home_id !== value.user?.home_id) client.clear();
    accepted.current = value;
    setSession(value); setError(null); setChecking(false);
  }, [client]);
  const load = useCallback(async (force = false) => {
    const current = ++generation.current;
    setChecking(true); setError(null);
    try { const value = await readSession(force); if (generation.current === current) accept(value); }
    catch (error) { if (generation.current === current) setError(error instanceof Error ? error.message : '登录状态读取失败。'); }
  }, [accept]);
  useEffect(() => {
    const current = ++generation.current;
    void readSession().then((value) => { if (generation.current === current) accept(value); },
      (error) => { if (generation.current === current) setError(error instanceof Error ? error.message : '登录状态读取失败。'); });
    return subscribeUnauthorized(() => {
      void client.cancelQueries();
      void load(true);
    });
  }, [accept, client, load]);
  useEffect(() => {
    if (!session || checking) return;
    const focus = () => { invalidateSession(); };
    const restored = (event: PageTransitionEvent) => { if (event.persisted) invalidateSession(); };
    window.addEventListener('focus', focus);
    window.addEventListener('pageshow', restored);
    return () => { window.removeEventListener('focus', focus); window.removeEventListener('pageshow', restored); };
  }, [checking, session]);
  async function adopt(value: AuthSession) {
    const current = ++generation.current;
    await client.cancelQueries();
    if (generation.current === current) accept(value);
  }
  async function logout() {
    if (transitioning) return;
    setTransitioning(true); setError(null);
    try { await adopt(await authApi.logout()); }
    catch (error) {
      const message = error instanceof Error ? error.message : '退出未完成，请重试。';
      await load(true);
      if (accepted.current?.user) setError(message);
    } finally { setTransitioning(false); }
  }
  const blocked = transitioning || checking || session === undefined;
  return <>
    {blocked && <main className={styles.page}>
      <section className={styles.card}>
        {error ? <Alert type="error" title="尚未确认账号状态" description={error} action={<Button onClick={() => { void load(true); }}>重试连接</Button>} />
          : <div role="status"><Spin /><p>正在读取账号与家庭…</p></div>}
      </section>
    </main>}
    {session && <div id="homemind-session-surface" hidden={blocked} inert={blocked}>
      <ConfigProvider getPopupContainer={popupContainer}>
      {session.user ? <SessionContext key={session.user.home_id} value={{ session: { ...session, user: session.user }, logout }}>{error && !blocked && <Alert type="error" title={error} />}{children}</SessionContext>
        : <Suspense fallback={<main className={styles.page}><Spin description="正在加载账号表单…" /></main>}><AuthForm onSession={adopt} /></Suspense>}
      </ConfigProvider>
    </div>}
  </>;
}
