import { useCallback, useEffect, useRef, useState } from 'react';
import { Satellite, WifiOff, Wifi, RefreshCw } from 'lucide-react';
import { useProbeTelemetry } from './hooks/useProbeTelemetry';
import { HeroSignalView } from './components/HeroSignalView';
import { StatusCards } from './components/StatusCards';
import { TelemetryDashboard } from './components/TelemetryDashboard';
import { CommandConsole } from './components/CommandConsole';
import { AgentPanel } from './components/AgentPanel';
import { OpenMctSection } from './components/OpenMctSection';
import { TwinLaunchSection } from './components/TwinLaunchSection';
import './styles.css';

export default function App() {
  const { snapshot, health, linkStatus, error, refreshHealth } = useProbeTelemetry();
  const [uplinkPulse, setUplinkPulse] = useState(false);
  const uplinkPulseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const triggerUplinkPulse = useCallback(() => {
    setUplinkPulse(true);
    if (uplinkPulseTimer.current) clearTimeout(uplinkPulseTimer.current);
    uplinkPulseTimer.current = setTimeout(() => {
      setUplinkPulse(false);
      uplinkPulseTimer.current = null;
    }, 900);
  }, []);

  useEffect(() => {
    const t = setInterval(refreshHealth, 5000);
    return () => clearInterval(t);
  }, [refreshHealth]);

  useEffect(() => {
    return () => {
      if (uplinkPulseTimer.current) clearTimeout(uplinkPulseTimer.current);
    };
  }, []);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><Satellite/> DeepRepair Mission Control <span>v1</span></div>
        <div className="topbar-right">
          <div className={`link-status ${linkStatus}`}>
            {linkStatus === 'online' ? <Wifi size={15}/> : <WifiOff size={15}/>} Probe Link: {linkStatus.toUpperCase()}
          </div>
          <button className="icon-button" onClick={() => refreshHealth()}><RefreshCw size={14}/> refresh</button>
        </div>
      </header>

      {error && <div className="error-banner">Probe connection error: {error}</div>}

      <main className="layout">
        <div className="hero-column">
          <HeroSignalView linkStatus={linkStatus} mode={snapshot?.mode} activeFault={snapshot?.active_fault} uplinkPulse={uplinkPulse} />
          <StatusCards snapshot={snapshot} />
          <OpenMctSection />
        </div>

        <div className="center-column">
          <TelemetryDashboard snapshot={snapshot} />
          <TwinLaunchSection />
        </div>

        <div className="right-column">
          <AgentPanel health={health} onUplink={triggerUplinkPulse} />
          <CommandConsole onUplink={triggerUplinkPulse} />
        </div>
      </main>
    </div>
  );
}
