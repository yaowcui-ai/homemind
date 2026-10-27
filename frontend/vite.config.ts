import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'HOMEMIND_');
  const target = process.env.HOMEMIND_API_PROXY_TARGET
    ?? env.HOMEMIND_API_PROXY_TARGET
    ?? 'http://127.0.0.1:8100';
  const targetUrl = new URL(target);
  if (!['http:', 'https:'].includes(targetUrl.protocol) || targetUrl.username || targetUrl.password) {
    throw new Error('后端代理配置无效，请使用不包含账号密码的 HTTP(S) 地址。');
  }

  return {
    plugins: [react()],
    server: {
      host: '127.0.0.1',
      port: 5174,
      strictPort: true,
      proxy: {
        '/api': {
          target: targetUrl.origin,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api(?=\/|$)/, ''),
          timeout: 85000,
          proxyTimeout: 85000,
        },
      },
    },
  };
});
