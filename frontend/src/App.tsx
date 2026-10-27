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
const viewLabels: Record<View, string> = { overview: '家庭概览', configuration: '家庭配置', tasks: '规则任务', preferences: '偏好设置' };

export default function App() {
  return <ConfigProvider locale={zhCN} theme={{ token: {
    colorPrimary: '#285b47', borderRadius: 10,
    fontFamily: 'Inter, "Microsoft YaHei", "PingFang SC", sans-serif',
  } }}>
    <AuthGate><Workspace /></AuthGate>
  </ConfigProvider>;
}

function Workspace() {
  const { session, logout } = useSession();
  const [view, setView] = useState<View>('overview');
  const [submission] = useState(() => new TaskSubmission());
  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <a href="/" className={styles.brand} aria-label="HomeMind 首页">
          <span className={styles.brandIcon}><HomeOutlined /></span>
          <span>HomeMind<span className={styles.brandCaption}>智能家居协同控制台</span></span>
        </a>
        <div className={styles.navLabel}>工作空间</div>
        <nav className={styles.navigation} aria-label="主导航">
          <button aria-label="家庭概览" className={view === 'overview' ? styles.activeNav : ''} onClick={() => setView('overview')}><HomeOutlined /> 家庭概览</button>
          <button aria-label="家庭配置" className={view === 'configuration' ? styles.activeNav : ''} onClick={() => setView('configuration')}><ApartmentOutlined /> 家庭配置</button>
          <button aria-label="规则任务" className={view === 'tasks' ? styles.activeNav : ''} onClick={() => setView('tasks')}><MessageOutlined /> 规则任务</button>
          <button aria-label="偏好设置" className={view === 'preferences' ? styles.activeNav : ''} onClick={() => setView('preferences')}><SettingOutlined /> 偏好设置</button>
        </nav>
        <div className={styles.sidebarNote}>
          <span className={styles.noteMark}>M3</span><strong>属于你自己的家</strong>
          <p>独立的家庭与偏好，<br />持续保存的每一次变化。</p>
        </div>
        <div className={styles.sidebarFoot}>HOME, THOUGHTFULLY CONNECTED</div>
      </aside>
      <main className={styles.main}>
        <header className={styles.topbar}>
          <div className={styles.breadcrumb}>工作空间 <span>/</span> {viewLabels[view]}</div>
          <div className={styles.accountActions}><span className={styles.stageBadge}><span /> 设备仿真</span><span title={session.user.username}>{session.user.username}</span><button onClick={() => { void logout(); }}>退出登录</button></div>
        </header>
        <section className={styles.hero}>
          <p className={styles.eyebrow}><span /> A MORE THOUGHTFUL HOME</p>
          <h1>让家，按你的节奏运转<span>。</span></h1>
          <p className={styles.heroText}>从开灯到调温，从窗户开合到人员进出，<br className={styles.mobileBreak} />每一次变化，都有可读取的状态。</p>
        </section>
        <div className={styles.mobileTabs} aria-label="视图切换">
          {(Object.entries(viewLabels) as [View, string][]).map(([key, label]) => <button key={key} className={view === key ? styles.selectedTab : ''} onClick={() => setView(key)}>{label}</button>)}
        </div>
        <Suspense fallback={<p role="status">正在加载家庭控制台…</p>}>
          {view === 'overview' || view === 'configuration' ? <SimulationDashboard view={view} homeId={session.user.home_id} debugEnabled={session.simulation_debug_enabled} />
            : view === 'tasks' ? <TasksPanel homeId={session.user.home_id} submission={submission} /> : <PreferencesPanel homeId={session.user.home_id} />}
        </Suspense>
        <div className={styles.healthFooter}><ConnectionCard /></div>
        <footer className={styles.footer}><span>HomeMind / 仿真参数用于功能验证，不能代替真实硬件测量</span><span>M3 · PERSONAL HOME</span></footer>
      </main>
    </div>
  );
}
