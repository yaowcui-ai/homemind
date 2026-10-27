import { CheckCircleFilled, CloudServerOutlined, ReloadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Button } from 'antd';
import { fetchHealth } from '../api/health';
import styles from '../App.module.css';

export default function ConnectionCard() {
  const health = useQuery({
    queryKey: ['health'], queryFn: fetchHealth, networkMode: 'always', retry: false,
    refetchOnWindowFocus: false, refetchOnReconnect: false,
  });
  const checking = health.isFetching;
  const connected = health.isSuccess && !health.isError && !checking;
  return (
    <section className={styles.connection} aria-label="后端连接">
      <div className={`${styles.statusIcon} ${checking ? styles.pending : connected ? styles.online : styles.offline}`}>
        {connected ? <CheckCircleFilled /> : <CloudServerOutlined />}
      </div>
      <p className={styles.statusTitle} role="status" aria-live="polite">
        {checking ? '正在检查连接…' : connected ? '后端已连接' : '连接未完成'}
      </p>
      <p className={styles.connectionText}>
        {checking ? '正在与 HomeMind 服务建立连接。' : connected ? '本地仿真服务已就绪。' : health.error?.message}
      </p>
      <div className={styles.connectionMeta}><span>HomeMind API</span><span>{connected ? `v${health.data.version}` : '等待响应'}</span></div>
      <Button block icon={<ReloadOutlined spin={checking} />} disabled={checking} onClick={() => { void health.refetch(); }}>重新检查</Button>
      <p className={styles.connectionHint}>设备与时间为本地仿真，尚未接入真实硬件；自然语言能力以模型配置和任务结果为准。</p>
    </section>
  );
}
