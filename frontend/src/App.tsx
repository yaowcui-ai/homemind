import { lazy, Suspense, useState } from 'react';
import { ApartmentOutlined, HomeOutlined, MessageOutlined, SettingOutlined } from '@ant-design/icons';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import ConnectionCard from './components/ConnectionCard';
import styles from './App.module.css';

const SimulationDashboard = lazy(() => import('./components/simulation/SimulationDashboard'));

export default function App() {
  const [view, setView] = useState<'overview' | 'configuration'>('overview');
  return <ConfigProvider locale={zhCN} theme={{ token: {
    colorPrimary: '#285b47', borderRadius: 10,
    fontFamily: 'Inter, "Microsoft YaHei", "PingFang SC", sans-serif',
  } }}>
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
          <button disabled title="后续阶段开放"><MessageOutlined /> 任务协作<span>待接入</span></button>
          <button disabled title="后续阶段开放"><SettingOutlined /> 偏好设置<span>待接入</span></button>
        </nav>
        <div className={styles.sidebarNote}>
          <span className={styles.noteMark}>M2</span><strong>让状态流动起来</strong>
          <p>配置你的房间与设备，<br />观察每一个动作的结果。</p>
        </div>
        <div className={styles.sidebarFoot}>HOME, THOUGHTFULLY CONNECTED</div>
      </aside>
      <main className={styles.main}>
        <header className={styles.topbar}>
          <div className={styles.breadcrumb}>工作空间 <span>/</span> {view === 'overview' ? '家庭概览' : '家庭配置'}</div>
          <span className={styles.stageBadge}><span /> 设备仿真</span>
        </header>
        <section className={styles.hero}>
          <p className={styles.eyebrow}><span /> A MORE THOUGHTFUL HOME</p>
          <h1>让家，按你的节奏运转<span>。</span></h1>
          <p className={styles.heroText}>从开灯到调温，从窗户开合到人员进出，<br className={styles.mobileBreak} />每一次变化，都有可读取的状态。</p>
        </section>
        <div className={styles.mobileTabs} aria-label="视图切换">
          <button className={view === 'overview' ? styles.selectedTab : ''} onClick={() => setView('overview')}>家庭概览</button>
          <button className={view === 'configuration' ? styles.selectedTab : ''} onClick={() => setView('configuration')}>家庭配置</button>
        </div>
        <Suspense fallback={<p role="status">正在加载家庭控制台…</p>}><SimulationDashboard view={view} /></Suspense>
        <div className={styles.healthFooter}><ConnectionCard /></div>
        <footer className={styles.footer}><span>HomeMind / 仿真参数用于功能验证，不能代替真实硬件测量</span><span>M2 · SIMULATION</span></footer>
      </main>
    </div>
  </ConfigProvider>;
}
