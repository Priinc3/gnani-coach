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
