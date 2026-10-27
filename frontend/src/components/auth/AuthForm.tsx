import { useRef, useState } from 'react';
import { Alert, Button, Form, Input } from 'antd';
import { HomeOutlined } from '@ant-design/icons';
import { authApi } from '../../api/auth';
import type { AuthSession, Credentials } from '../../api/auth.types';
import styles from './Auth.module.css';

export default function AuthForm({ onSession }: { onSession: (session: AuthSession) => Promise<void> }) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitting = useRef(false);
  const [form] = Form.useForm<Credentials>();
  async function submit(values: Credentials) {
    if (submitting.current) return;
    submitting.current = true; setPending(true); setError(null);
    try { await onSession(await authApi[mode](values)); }
    catch (error) { setError(error instanceof Error ? error.message : '账号操作未完成，请重试。'); }
    finally { submitting.current = false; setPending(false); }
  }
  return <main className={styles.page}>
    <section className={styles.card} aria-label="账号入口">
      <div className={styles.brand}><HomeOutlined /><span>HomeMind<small>你的家，有自己的节奏</small></span></div>
      <p className={styles.eyebrow}>A MORE THOUGHTFUL HOME</p>
      <h1>{mode === 'login' ? '欢迎回家' : '从你的第一个家开始'}</h1>
      <p className={styles.description}>{mode === 'login' ? '登录后继续管理你的房间、设备与任务。' : '注册后获得独立的两房十二实体模板，随时可以修改。'}</p>
      <div className={styles.tabs}>
        <Button type={mode === 'login' ? 'primary' : 'default'} disabled={pending} onClick={() => { setMode('login'); setError(null); form.resetFields(['password']); }}>登录</Button>
        <Button type={mode === 'register' ? 'primary' : 'default'} disabled={pending} onClick={() => { setMode('register'); setError(null); form.resetFields(['password']); }}>注册</Button>
      </div>
      {error && <Alert type="error" showIcon title={error} />}
      <Form form={form} layout="vertical" disabled={pending} onFinish={(values) => { void submit(values); }}>
        <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }, { pattern: /^[a-zA-Z0-9_]{3,32}$/, message: '使用 3—32 位字母、数字或下划线' }]}>
          <Input autoComplete="username" maxLength={32} placeholder="字母、数字或下划线" />
        </Form.Item>
        <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }, { min: mode === 'register' ? 12 : 1, max: 128, message: '密码长度为 12—128 个字符' }]}>
          <Input.Password autoComplete={mode === 'register' ? 'new-password' : 'current-password'} maxLength={128} placeholder={mode === 'register' ? '至少 12 个字符' : '输入你的密码'} />
        </Form.Item>
        <Button block type="primary" htmlType="submit" loading={pending}>{mode === 'login' ? '登录我的家庭' : '注册并创建家庭'}</Button>
      </Form>
      <p className={styles.foot}>每个账号拥有独立家庭。当前设备与温度为仿真数据。</p>
    </section>
  </main>;
}
