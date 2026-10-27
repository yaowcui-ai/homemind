import { lazy, Suspense, useState } from 'react';
import { ApartmentOutlined, HomeOutlined, MessageOutlined, SettingOutlined } from '@ant-design/icons';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import ConnectionCard from './components/ConnectionCard';
import AuthGate from './components/auth/AuthGate';
import { useSession } from './components/auth/sessionContext';
import { TaskSubmission } from './api/tasks';
import styles from './App.module.css';

const SimulationDashboard = lazy(() => import('./components/simulation/SimulationDashboard'));
const TasksPanel = lazy(() => import('./components/tasks/TasksPanel'));
const PreferencesPanel = lazy(() => import('./components/tasks/PreferencesPanel'));
type View = 'overview' | 'configuration' | 'tasks' | 'preferences';
const viewLabels: Record<View, string> = { overview: '家庭概览', configuration: '家庭配置', tasks: '任务助手', preferences: '偏好设置' };
const viewDescriptions: Record<View, string> = { overview: '掌握房间状态，清晰控制每一个设备。', configuration: '管理房间、实体与主读数，配置适合自己的家。', tasks: '表达生活需求或选择规则，确认范围，逐项核验结果。', preferences: '保存舒适与习惯，为新任务提供默认设置。' };

export default function App() {
  return <ConfigProvider locale={zhCN} theme={{ token: {
    colorPrimary: '#2563EB', colorInfo: '#2563EB', colorSuccess: '#0F766E',
    colorWarning: '#92400E', colorError: '#B91C1C', colorText: '#172B4D',
    colorTextSecondary: '#5E6C84', colorBorder: '#DFE5EF', colorBgContainer: '#FFFFFF',
    borderRadius: 8, controlHeight: 38,
    fontFamily: 'Inter, "Noto Sans SC", "Microsoft YaHei", "PingFang SC", sans-serif',
  } }}>
    <AuthGate><Workspace /></AuthGate>
  </ConfigProvider>;
}

function Workspace() {
  const { session, logout } = useSession();
  const [view, setView] = useState<View>('overview');
  const [submission] = useState(() => new TaskSubmission(session.user.home_id));
  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <a href="/" className={styles.brand} aria-label="HomeMind 首页">
          <span className={styles.brandIcon}><HomeOutlined /></span>
          <span>HomeMind<span className={styles.brandCaption}>智能家居控制台</span></span>
        </a>
        <div className={styles.navLabel}>工作空间</div>
        <nav className={styles.navigation} aria-label="主导航">
          <button aria-label="家庭概览" className={view === 'overview' ? styles.activeNav : ''} onClick={() => setView('overview')}><HomeOutlined /> 家庭概览</button>
          <button aria-label="家庭配置" className={view === 'configuration' ? styles.activeNav : ''} onClick={() => setView('configuration')}><ApartmentOutlined /> 家庭配置</button>
          <button aria-label="任务助手" className={view === 'tasks' ? styles.activeNav : ''} onClick={() => setView('tasks')}><MessageOutlined /> 任务助手</button>
          <button aria-label="偏好设置" className={view === 'preferences' ? styles.activeNav : ''} onClick={() => setView('preferences')}><SettingOutlined /> 偏好设置</button>
        </nav>
        <div className={styles.sidebarNote}>
          <span className={styles.noteMark}><HomeOutlined /></span><strong>属于你自己的家</strong>
          <p>独立的家庭与偏好，<br />持续保存的每一次变化。</p>
        </div>
        <div className={styles.sidebarFoot}>M4 · 设备仿真</div>
      </aside>
      <main className={styles.main}>
        <header className={styles.topbar}>
          <div className={styles.breadcrumb}>工作空间 <span>/</span> {viewLabels[view]}</div>
          <div className={styles.accountActions}><span className={styles.stageBadge}><span /> 设备仿真</span><span title={session.user.username}>{session.user.username}</span><button onClick={() => { void logout(); }}>退出登录</button></div>
        </header>
        <section className={styles.hero}>
          <h1>{viewLabels[view]}</h1>
          <p className={styles.heroText}>{viewDescriptions[view]}</p>
        </section>
        <div className={styles.mobileTabs} aria-label="视图切换">
          {(Object.entries(viewLabels) as [View, string][]).map(([key, label]) => <button key={key} className={view === key ? styles.selectedTab : ''} onClick={() => setView(key)}>{label}</button>)}
        </div>
        <Suspense fallback={<p role="status">正在加载家庭控制台…</p>}>
          {view === 'overview' || view === 'configuration' ? <SimulationDashboard view={view} homeId={session.user.home_id} debugEnabled={session.simulation_debug_enabled} />
            : view === 'tasks' ? <TasksPanel homeId={session.user.home_id} submission={submission} debugEnabled={session.simulation_debug_enabled} /> : <PreferencesPanel homeId={session.user.home_id} />}
        </Suspense>
        <div className={styles.healthFooter}><ConnectionCard /></div>
        <footer className={styles.footer}><span>HomeMind / 仿真参数用于功能验证，不能代替真实硬件测量</span><span>M4 · PERSONAL HOME</span></footer>
      </main>
    </div>
  );
}
