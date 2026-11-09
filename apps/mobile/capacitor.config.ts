import type { CapacitorConfig } from '@capacitor/cli';

const appUrl = process.env.APP_URL;

if (!appUrl) {
  throw new Error(
    'APP_URL is required: set it to the https:// URL of the hosted Speaking Coach web app.'
  );
}

if (!appUrl.startsWith('https://')) {
  throw new Error(
    `APP_URL must start with https:// (got "${appUrl}"). Cleartext HTTP is not allowed.`
  );
}

const config: CapacitorConfig = {
  appId: 'com.gnanicoach.app',
  appName: 'Speaking Coach',
  webDir: 'www',
  loggingBehavior: 'none',
  // The app background, so the WebView and the native window never flash a
  // different colour at the edges.
  backgroundColor: '#f7f6f2',
  // SystemBars is bundled with @capacitor/core 8.6.0. `css` injects the
  // --safe-area-inset-* variables the web layout uses as a fallback for
  // env(safe-area-inset-*). Source:
  // <https://capacitorjs.com/docs/apis/system-bars> (checked 2026-11-09).
  plugins: {
    SystemBars: {
      insetsHandling: 'css',
      style: 'DEFAULT',
      hidden: false
    }
  },
  server: {
    url: appUrl,
    androidScheme: 'https',
    errorPath: 'error.html'
  },
  android: {
    webContentsDebuggingEnabled: false
  }
};

export default config;
