import {
  ApartmentOutlined, ArrowRightOutlined, CheckCircleFilled, CloudServerOutlined,
  HomeOutlined, MessageOutlined, ReloadOutlined, SettingOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Button, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { fetchHealth } from './api/health';
import styles from './App.module.css';

function HomeSketch() {
  return (
    <svg viewBox="0 0 580 340" className={styles.sketch} role="img" aria-label="客厅与卧室默认模板示意">
      <defs>
        <pattern id="grid" width="18" height="18" patternUnits="userSpaceOnUse">
          <circle cx="1" cy="1" r="0.7" fill="#c3d1c6" />
        </pattern>
      </defs>
      <rect width="580" height="340" fill="url(#grid)" />
      <rect x="52" y="44" width="476" height="246" rx="7" fill="#f8faf4" stroke="#698975" strokeWidth="3" />
      <path d="M326 46V174 M326 228V288" stroke="#698975" strokeWidth="3" />
      <path d="M326 174A54 54 0 0 0 380 228H326" fill="none" stroke="#a2b7a5" strokeWidth="1.5" />
      <rect x="89" y="87" width="134" height="55" rx="10" fill="#d4e2d2" stroke="#90a88e" />
      <rect x="80" y="95" width="18" height="57" rx="5" fill="#d4e2d2" stroke="#90a88e" />
      <rect x="214" y="95" width="18" height="57" rx="5" fill="#d4e2d2" stroke="#90a88e" />
      <path d="M157 88V139" stroke="#a7bda5" />
      <rect x="128" y="168" width="83" height="40" rx="15" fill="#ece3c9" stroke="#c7b98e" />
      <circle cx="279" cy="92" r="17" fill="#dfE9cd" stroke="#a4b68a" />
      <path d="M279 80V103 M269 86L289 99 M289 86L270 99" stroke="#a4b68a" />
      <rect x="387" y="87" width="96" height="121" rx="7" fill="#e7dfcc" stroke="#baac8c" />
      <rect x="394" y="95" width="37" height="24" rx="5" fill="#f7f4e9" stroke="#c6b99d" />
      <rect x="440" y="95" width="36" height="24" rx="5" fill="#f7f4e9" stroke="#c6b99d" />
      <path d="M388 130H482" stroke="#c6b99d" />
      <rect x="370" y="95" width="11" height="27" rx="2" fill="#d4e2d2" />
      <rect x="490" y="95" width="11" height="27" rx="2" fill="#d4e2d2" />
      <rect x="135" y="40" width="94" height="8" fill="#e1edde" stroke="#89a28b" />
      <rect x="400" y="40" width="70" height="8" fill="#e1edde" stroke="#89a28b" />
      <text x="156" y="250" textAnchor="middle" fill="#335746" fontSize="17" fontWeight="600">客厅</text>
      <text x="435" y="250" textAnchor="middle" fill="#335746" fontSize="17" fontWeight="600">卧室</text>
      <text x="156" y="272" textAnchor="middle" fill="#7c8d7a" fontSize="11">6 个默认实体</text>
      <text x="435" y="272" textAnchor="middle" fill="#7c8d7a" fontSize="11">6 个默认实体</text>
    </svg>
  );
}

export default function App() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    networkMode: 'always',
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  const checking = health.isFetching;
  const connected = health.isSuccess && !health.isError && !checking;
  const statusText = checking ? '正在检查连接…' : connected ? '后端已连接' : '连接未完成';
  const statusClass = checking ? styles.pending : connected ? styles.online : styles.offline;

  return (
    <ConfigProvider locale={zhCN} theme={{
      token: {
        colorPrimary: '#285b47', borderRadius: 10,
        fontFamily: 'Inter, "Microsoft YaHei", "PingFang SC", sans-serif',
      },
    }}>
      <div className={styles.shell}>
        <aside className={styles.sidebar}>
          <a href="/" className={styles.brand} aria-label="HomeMind 首页">
            <span className={styles.brandIcon}><HomeOutlined /></span>
            <span>HomeMind<span className={styles.brandCaption}>智能家居协同控制台</span></span>
          </a>
          <div className={styles.navLabel}>工作空间</div>
          <nav className={styles.navigation} aria-label="主导航">
            <a href="/" className={styles.activeNav} aria-current="page"><HomeOutlined /> 家庭概览</a>
            <button disabled title="后续阶段开放"><ApartmentOutlined /> 家庭配置<span>待接入</span></button>
            <button disabled title="后续阶段开放"><MessageOutlined /> 任务协作<span>待接入</span></button>
            <button disabled title="后续阶段开放"><SettingOutlined /> 偏好设置<span>待接入</span></button>
          </nav>
          <div className={styles.sidebarNote}>
            <span className={styles.noteMark}>M1</span>
            <strong>从连接开始</strong>
            <p>先打通网页与服务，<br />再让家的状态流动起来。</p>
          </div>
          <div className={styles.sidebarFoot}>HOME, THOUGHTFULLY CONNECTED</div>
        </aside>

        <main className={styles.main}>
          <header className={styles.topbar}>
            <div className={styles.breadcrumb}>工作空间 <span>/</span> 家庭概览</div>
            <span className={styles.stageBadge}><span /> 工程基础</span>
          </header>

          <section className={styles.hero}>
            <p className={styles.eyebrow}><span /> A MORE THOUGHTFUL HOME</p>
            <h1>让家，按你的节奏运转<span>。</span></h1>
            <p className={styles.heroText}>从家庭状态到可验证的设备行动，<br className={styles.mobileBreak} />让每一次协作都有据可循。</p>
          </section>

          <section className={styles.summary} aria-label="默认设计概览">
            <div><span>默认房间</span><strong>02<small>间</small></strong><p>客厅与卧室，可按需调整</p></div>
            <div><span>初始实体</span><strong>12<small>个</small></strong><p>6 个控制实体 · 6 个传感实体</p></div>
            <div><span>协作角色</span><strong>03<small>类</small></strong><p>协调 · 舒适 · 节能</p></div>
          </section>

          <div className={styles.workspace}>
            <section className={styles.connection} aria-label="后端连接">
              <div className={styles.cardHeader}>
                <span className={styles.sectionLabel}>连接状态</span>
                <CloudServerOutlined className={styles.serverIcon} />
              </div>
              <div className={`${styles.statusIcon} ${statusClass}`}>
                {connected ? <CheckCircleFilled /> : <CloudServerOutlined />}
              </div>
              <p className={styles.statusTitle} role="status" aria-live="polite">{statusText}</p>
              <p className={styles.connectionText}>
                {checking ? '正在与 HomeMind 服务建立连接。'
                  : connected ? '网页与 API 已连通，可以继续搭建你的家庭。'
                    : health.error?.message ?? '请启动后端服务，然后重新检查。'}
              </p>
              <div className={styles.connectionMeta}>
                <span><i className={connected ? styles.greenDot : styles.grayDot} /> HomeMind API</span>
                <span>{connected ? `v${health.data.version}` : '等待响应'}</span>
              </div>
              <Button
                block size="large" icon={<ReloadOutlined spin={checking} />}
                disabled={checking} onClick={() => { void health.refetch(); }}
              >重新检查</Button>
              <p className={styles.connectionHint}>此状态仅代表 API 连通，尚未接入设备与 Agent。</p>
            </section>

            <section className={styles.template} aria-label="默认家庭模板">
              <div className={styles.cardHeader}>
                <div><span className={styles.sectionLabel}>家的初始模样</span><h2>两个房间，一个开始</h2></div>
                <span className={styles.previewBadge}>模板预览</span>
              </div>
              <HomeSketch />
              <div className={styles.templateFoot}>
                <span>设备仿真将在下一阶段接入。</span>
                <span className={styles.templateArrow} aria-hidden="true"><ArrowRightOutlined /></span>
              </div>
            </section>
          </div>

          <section className={styles.nextStep} aria-label="后续阶段说明">
            <span className={styles.stepNumber}>NEXT</span>
            <div><strong>下一步，认识你的家</strong><p>配置房间与实体，用可复现的仿真观察每一次变化。</p></div>
            <span className={styles.readOnlyLabel}>当前为工程基础阶段</span>
          </section>
          <footer className={styles.footer}><span>HomeMind / 用清晰的状态，连接舒适的生活</span><span>M1 · FOUNDATION</span></footer>
        </main>
      </div>
    </ConfigProvider>
  );
}
