const { app, BrowserWindow, dialog, shell } = require('electron');
const path = require('path');

function readArg(name) {
  const index = process.argv.indexOf(name);
  if (index === -1 || index + 1 >= process.argv.length) return '';
  return process.argv[index + 1];
}

const appId = readArg('--app-id');
const appName = readArg('--name') || 'Web App';
const appUrl = readArg('--url');
const profile = readArg('--profile');
const icon = readArg('--icon');

if (!appId || !appUrl || !profile) {
  console.error('Missing required arguments: --app-id, --url, --profile');
  process.exit(2);
}

app.setName(appName);
app.setAppUserModelId(appId);
app.setPath('userData', profile);

app.commandLine.appendSwitch('no-sandbox');
app.commandLine.appendSwitch('disable-gpu');
app.commandLine.appendSwitch('disable-gpu-compositing');
app.commandLine.appendSwitch('disable-renderer-backgrounding');
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.commandLine.appendSwitch('enable-features', 'VaapiVideoDecoder');

let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 980,
    height: 700,
    minWidth: 640,
    minHeight: 440,
    title: appName,
    icon: icon || undefined,
    show: false,
    backgroundColor: '#111111',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      backgroundThrottling: false,
    },
  });

  mainWindow.setMenuBarVisibility(false);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://') || url.startsWith('https://')) {
      mainWindow.loadURL(url);
      return { action: 'deny' };
    }
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    dialog.showErrorBox(
      `${appName} stopped responding`,
      `The web process ended with reason: ${details.reason}. Try reopening the app.`
    );
  });

  mainWindow.loadURL(appUrl).catch((error) => {
    dialog.showErrorBox(`${appName} could not open`, error.message);
  });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  app.quit();
});
