import React, { useEffect } from 'react';
import ReactDOM from 'react-dom/client';
import { ArrowLeft, RefreshCw, Satellite, Wifi, WifiOff } from 'lucide-react';
import { useProbeTelemetry } from './hooks/useProbeTelemetry';
import { Twin3DPanel } from './components/twin/Twin3DPanel';
import './styles.css';

function TwinPage() {
  const { snapshot, linkStatus, error, refreshHealth } = useProbeTelemetry();

  useEffect(() => {
    const timer = window.setInterval(refreshHealth, 5000);
    return () => window.clearInterval(timer);
  }, [refreshHealth]);

  return (
    <div className="app-shell twin-page-shell">
      <header className="topbar">
        <div className="brand"><Satellite /> DeepRepair Ground Twin Testbed <span>v1</span></div>
        <div className="topbar-right">
          <a className="icon-button" href="/">
            <ArrowLeft size={14} /> Mission Control
          </a>
          <div className={`link-status ${linkStatus}`}>
            {linkStatus === 'online' ? <Wifi size={15} /> : <WifiOff size={15} />} Probe Link: {linkStatus.toUpperCase()}
          </div>
          <button className="icon-button" onClick={() => refreshHealth()} type="button">
            <RefreshCw size={14} /> refresh
          </button>
        </div>
      </header>

      {error && <div className="error-banner">Probe connection error: {error}</div>}

      <main className="twin-page-main">
        <Twin3DPanel snapshot={snapshot} />
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('twin-root')!).render(
  <React.StrictMode>
    <TwinPage />
  </React.StrictMode>
);
