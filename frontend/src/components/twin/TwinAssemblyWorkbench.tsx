import { useMemo, useState } from 'react';
import { Bot, Cable, CheckCircle2, CircuitBoard, Link2, Move3D, Plus, Puzzle, Redo2, RotateCw, ShieldAlert, Undo2, Unlink, Wrench, X } from 'lucide-react';
import type { useTwinTestbed } from '../../hooks/useTwinTestbed';
import type { ComponentFaultTemplate, TwinComponentInstance, TwinComponentLink, TwinComponentPort } from '../../types/twin';

type TwinTestbedController = ReturnType<typeof useTwinTestbed>;

export function TwinAssemblyWorkbench({ testbed }: { testbed: TwinTestbedController }) {
  const assembly = testbed.assembly;
  const selected = testbed.selectedComponent;
  const installed = assembly?.components.filter((component) => component.install_state !== 'removed') ?? [];
  const links = assembly?.links ?? [];
  const invalidComponents = new Set((assembly?.validation.issues ?? []).map((issue) => issue.component_id).filter(Boolean));
  const invalidLinks = new Set((assembly?.validation.issues ?? []).map((issue) => issue.link_id).filter(Boolean));
  const catalogEntries = useMemo(() => readCatalogEntries(testbed.catalog?.catalog), [testbed.catalog]);
  const [catalogId, setCatalogId] = useState('payload.sensor');
  const [replaceCatalogId, setReplaceCatalogId] = useState('payload.sensor');
  const [fromComponent, setFromComponent] = useState('');
  const [fromPort, setFromPort] = useState('');
  const [toComponent, setToComponent] = useState('');
  const [toPort, setToPort] = useState('');
  const firstTemplate = selected?.fault_templates[0] ?? null;
  const chosenFromComponent = findComponent(installed, fromComponent) ?? selected ?? installed[0] ?? null;
  const chosenToComponent = findComponent(installed, toComponent) ?? installed.find((component) => component.instance_id !== chosenFromComponent?.instance_id) ?? null;
  const chosenFromPort = findPort(chosenFromComponent, fromPort) ?? chosenFromComponent?.ports[0] ?? null;
  const chosenToPort = findPort(chosenToComponent, toPort) ?? chosenToComponent?.ports[0] ?? null;
  const linkMedium = chosenFromPort?.kind ?? chosenToPort?.kind ?? 'data';

  const nudge = (axis: 'x' | 'y' | 'z', delta: number) => {
    if (!selected) return;
    testbed.transformComponent(selected.instance_id, {
      position: { ...selected.position, [axis]: Number(selected.position?.[axis] ?? 0) + delta }
    });
  };
  const rotateZ = () => {
    if (!selected) return;
    testbed.transformComponent(selected.instance_id, {
      rotation: { ...selected.rotation, z: Number(selected.rotation?.z ?? 0) + 0.25 }
    });
  };
  const scaleSelected = (delta: number) => {
    if (!selected) return;
    const base = Number(selected.scale?.x ?? 1);
    const next = Math.max(0.4, Math.min(2.4, base + delta));
    testbed.transformComponent(selected.instance_id, { scale: { x: next, y: next, z: next } });
  };
  const addCatalogComponent = () => {
    const count = installed.length + 1;
    const entry = catalogEntries.find((item) => item.id === catalogId);
    testbed.addComponent({
      catalog_id: catalogId,
      display_name: entry?.displayName,
      position: { x: -1.4 + (count % 5) * 0.42, y: 1.05, z: 0.9 + Math.floor(count / 5) * 0.28 }
    });
  };
  const createLink = () => {
    if (!chosenFromComponent || !chosenToComponent || !chosenFromPort || !chosenToPort) return;
    testbed.addLink({
      from_component: chosenFromComponent.instance_id,
      from_port: chosenFromPort.port_id,
      to_component: chosenToComponent.instance_id,
      to_port: chosenToPort.port_id,
      medium: linkMedium
    });
  };

  return (
    <div className="assembly-workbench">
      <div className="assembly-workbench-header">
        <div>
          <span className="eyebrow">Modular component graph</span>
          <strong><Puzzle size={14} /> Assembly Workbench</strong>
        </div>
        <div className="assembly-workbench-actions">
          <button disabled={!assembly?.undo_available || Boolean(testbed.loading)} onClick={testbed.undoAssembly} title="Undo" type="button"><Undo2 size={14} /></button>
          <button disabled={!assembly?.redo_available || Boolean(testbed.loading)} onClick={testbed.redoAssembly} title="Redo" type="button"><Redo2 size={14} /></button>
          <button disabled={!testbed.session || Boolean(testbed.loading)} onClick={testbed.validateAssembly} title="Validate" type="button"><CheckCircle2 size={14} /></button>
        </div>
      </div>

      <div className={`assembly-status-strip ${assembly?.validation.ok ? 'valid' : 'invalid'}`}>
        <span>{assembly ? `v${assembly.version}` : 'v--'}</span>
        <strong>{assembly?.validation.ok ? 'VALID' : `${assembly?.validation.blocking_count ?? 0} BLOCKERS`}</strong>
        <code>{assembly?.assembly_digest ? assembly.assembly_digest.slice(0, 12) : 'no-digest'}</code>
      </div>

      <div className="component-palette">
        <select disabled={!testbed.session || Boolean(testbed.loading)} onChange={(event) => setCatalogId(event.target.value)} value={catalogId}>
          {catalogEntries.map((entry) => (
            <option key={entry.id} value={entry.id}>{entry.displayName}</option>
          ))}
        </select>
        <button disabled={!testbed.session || Boolean(testbed.loading)} onClick={addCatalogComponent} type="button">
          <Plus size={13} /> Add
        </button>
        <button disabled={!testbed.session || Boolean(testbed.loading)} onClick={testbed.addSpareSensor} type="button">
          <Plus size={13} /> Spare sensor
        </button>
      </div>

      <div className="assembly-graph-strip">
        {installed.map((component) => (
          <ComponentChip
            component={component}
            invalid={invalidComponents.has(component.instance_id)}
            key={component.instance_id}
            onSelect={() => testbed.selectComponent(component.instance_id)}
            selected={component.instance_id === assembly?.selected_component_id}
          />
        ))}
      </div>

      <div className="assembly-detail-grid">
        <div className="assembly-selected-card">
          <div className="assembly-selected-title">
            <CircuitBoard size={15} />
            <span>{selected ? selected.display_name : 'No component selected'}</span>
            {selected && <em>{selected.subsystem}</em>}
          </div>
          {selected ? (
            <>
              <div className="assembly-kv">
                <span>Instance</span><strong>{selected.instance_id}</strong>
                <span>Slot</span><strong>{selected.slot}</strong>
                <span>Health</span><strong className={`health-${selected.health_state}`}>{selected.health_state}</strong>
                <span>Ports</span><strong>{selected.ports.map((port) => `${port.port_id}:${port.kind}${port.required ? '*' : ''}`).join(', ') || '--'}</strong>
              </div>
              <div className="transform-toolbar">
                <button disabled={Boolean(testbed.loading)} onClick={() => nudge('x', -0.2)} title="Move -X" type="button"><Move3D size={13} /> X-</button>
                <button disabled={Boolean(testbed.loading)} onClick={() => nudge('x', 0.2)} title="Move +X" type="button"><Move3D size={13} /> X+</button>
                <button disabled={Boolean(testbed.loading)} onClick={() => nudge('y', 0.2)} title="Move +Y" type="button"><Move3D size={13} /> Y+</button>
                <button disabled={Boolean(testbed.loading)} onClick={rotateZ} title="Rotate Z" type="button"><RotateCw size={13} /></button>
                <button disabled={Boolean(testbed.loading)} onClick={() => scaleSelected(0.1)} title="Scale up" type="button">S+</button>
                <button disabled={Boolean(testbed.loading)} onClick={() => scaleSelected(-0.1)} title="Scale down" type="button">S-</button>
              </div>
              <div className="component-parameter-row">
                <button disabled={Boolean(testbed.loading)} onClick={() => testbed.updateSelectedParameters({ load_w: 0.08 })} type="button">low load</button>
                {selected.catalog_id === 'payload.sensor' && (
                  <button disabled={Boolean(testbed.loading)} onClick={() => testbed.updateSelectedParameters({ primary: !Boolean(selected.parameters.primary) })} type="button">
                    {selected.parameters.primary ? 'make backup' : 'make primary'}
                  </button>
                )}
                <select disabled={Boolean(testbed.loading)} onChange={(event) => setReplaceCatalogId(event.target.value)} value={replaceCatalogId}>
                  {catalogEntries.map((entry) => <option key={entry.id} value={entry.id}>{entry.displayName}</option>)}
                </select>
                <button disabled={Boolean(testbed.loading)} onClick={() => testbed.replaceSelectedComponent(replaceCatalogId)} type="button">replace</button>
              </div>
              <div className="fault-template-row">
                {selected.fault_templates.slice(0, 3).map((template) => (
                  <FaultTemplateButton
                    disabled={Boolean(testbed.loading)}
                    key={template.template_id}
                    onInject={() => testbed.injectSelectedFault(template)}
                    template={template}
                  />
                ))}
              </div>
              <div className="assembly-selected-actions">
                <button disabled={!firstTemplate || Boolean(testbed.loading)} onClick={() => testbed.injectSelectedFault(firstTemplate)} type="button">
                  <ShieldAlert size={13} /> Inject fault
                </button>
                <button disabled={Boolean(testbed.loading)} onClick={testbed.requestTroubleshooting} type="button">
                  <Bot size={13} /> Troubleshoot
                </button>
                <button disabled={Boolean(testbed.loading)} onClick={testbed.removeSelectedComponent} type="button">
                  <X size={13} /> Remove
                </button>
              </div>
            </>
          ) : (
            <p>Freeze a baseline and select an installed node.</p>
          )}
        </div>

        <div className="assembly-link-card">
          <div className="assembly-selected-title">
            <Cable size={15} />
            <span>Ports</span>
            <em>{links.filter((link) => link.enabled).length} links</em>
          </div>
          <div className="link-editor">
            <PortPicker components={installed} componentId={chosenFromComponent?.instance_id ?? ''} portId={chosenFromPort?.port_id ?? ''} onComponent={setFromComponent} onPort={setFromPort} />
            <PortPicker components={installed} componentId={chosenToComponent?.instance_id ?? ''} portId={chosenToPort?.port_id ?? ''} onComponent={setToComponent} onPort={setToPort} />
            <button disabled={!chosenFromComponent || !chosenToComponent || Boolean(testbed.loading)} onClick={createLink} type="button"><Link2 size={13} /> Link</button>
          </div>
          <div className="assembly-link-list">
            {links.slice(0, 10).map((link) => (
              <LinkRow invalid={invalidLinks.has(link.link_id)} key={link.link_id} link={link} onRemove={() => testbed.removeLink(link.link_id)} />
            ))}
            {!links.length && <small>No links yet.</small>}
          </div>
        </div>
      </div>

      {assembly && !assembly.validation.ok && (
        <div className="validation-list">
          {assembly.validation.issues.slice(0, 5).map((issue) => (
            <div key={`${issue.code}-${issue.component_id ?? issue.link_id ?? issue.port_id ?? issue.message}`}>
              <strong>{issue.code}</strong>
              <span>{issue.message}</span>
            </div>
          ))}
        </div>
      )}

      {testbed.troubleshooting && (
        <div className="troubleshooting-card">
          <div className="assembly-selected-title"><Wrench size={15} /><span>Gemma Troubleshooting</span><em>{testbed.troubleshooting.source}</em></div>
          <p>{readGemmaSummary(testbed.troubleshooting.gemma) ?? testbed.troubleshooting.summary}</p>
          <div className="trouble-columns">
            <div>
              <span className="eyebrow">Suspects</span>
              {testbed.troubleshooting.suspects.slice(0, 3).map((suspect) => (
                <div className="suspect-row" key={String(suspect.component_id ?? suspect.display_name)}>
                  <strong>{String(suspect.display_name ?? suspect.component_id ?? 'component')}</strong>
                  <span>{Math.round(Number(suspect.confidence ?? 0) * 100)}%</span>
                </div>
              ))}
            </div>
            <div>
              <span className="eyebrow">Procedure</span>
              {testbed.troubleshooting.procedure.slice(0, 4).map((step, index) => (
                <div className="procedure-row" key={`${index}-${step}`}>{index + 1}. {step}</div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ComponentChip({ component, invalid, onSelect, selected }: { component: TwinComponentInstance; invalid: boolean; onSelect: () => void; selected: boolean }) {
  return (
    <button className={`component-chip ${selected ? 'selected' : ''} ${invalid ? 'invalid' : ''} ${component.health_state}`} onClick={onSelect} type="button">
      <span>{subsystemIcon(component.subsystem)}</span>
      <strong>{component.display_name}</strong>
      <em>{component.health_state}</em>
    </button>
  );
}

function PortPicker({
  componentId,
  components,
  onComponent,
  onPort,
  portId
}: {
  componentId: string;
  components: TwinComponentInstance[];
  onComponent: (value: string) => void;
  onPort: (value: string) => void;
  portId: string;
}) {
  const component = findComponent(components, componentId) ?? components[0] ?? null;
  return (
    <div className="port-picker">
      <select onChange={(event) => onComponent(event.target.value)} value={component?.instance_id ?? ''}>
        {components.map((item) => <option key={item.instance_id} value={item.instance_id}>{item.display_name}</option>)}
      </select>
      <select onChange={(event) => onPort(event.target.value)} value={portId}>
        {(component?.ports ?? []).map((port) => <option key={port.port_id} value={port.port_id}>{port.port_id}:{port.kind}</option>)}
      </select>
    </div>
  );
}

function LinkRow({ invalid, link, onRemove }: { invalid: boolean; link: TwinComponentLink; onRemove: () => void }) {
  return (
    <div className={`assembly-link ${invalid ? 'invalid' : ''}`}>
      <span>{link.from_component}.{link.from_port}</span>
      <strong>→</strong>
      <span>{link.to_component}.{link.to_port}</span>
      <em>{link.medium}</em>
      <button onClick={onRemove} title="Unlink" type="button"><Unlink size={12} /></button>
    </div>
  );
}

function FaultTemplateButton({ disabled, onInject, template }: { disabled: boolean; onInject: () => void; template: ComponentFaultTemplate }) {
  return (
    <button disabled={disabled} onClick={onInject} title={template.description} type="button">
      <ShieldAlert size={12} />
      <span>{template.label}</span>
    </button>
  );
}

function readCatalogEntries(catalog?: Record<string, unknown> | null): Array<{ id: string; displayName: string }> {
  const entries = Object.entries(catalog ?? {});
  if (!entries.length) return [{ id: 'payload.sensor', displayName: 'Thermal/Spectral Sensor' }];
  return entries.map(([id, value]) => ({
    id,
    displayName: readDisplayName(value) ?? id
  }));
}

function readDisplayName(value: unknown): string | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const display = (value as Record<string, unknown>).display_name;
  return typeof display === 'string' ? display : null;
}

function findComponent(components: TwinComponentInstance[], componentId?: string): TwinComponentInstance | null {
  return components.find((component) => component.instance_id === componentId) ?? null;
}

function findPort(component: TwinComponentInstance | null, portId?: string): TwinComponentPort | null {
  return component?.ports.find((port) => port.port_id === portId) ?? null;
}

function subsystemIcon(subsystem: string): string {
  if (subsystem === 'power') return 'PWR';
  if (subsystem === 'thermal') return 'THM';
  if (subsystem === 'comms') return 'COM';
  if (subsystem === 'computer') return 'CPU';
  if (subsystem === 'sensor') return 'SNS';
  return 'PAY';
}

function readGemmaSummary(gemma?: Record<string, unknown> | null): string | null {
  const troubleshooting = gemma?.troubleshooting;
  if (!troubleshooting || typeof troubleshooting !== 'object' || Array.isArray(troubleshooting)) return null;
  const value = (troubleshooting as Record<string, unknown>).summary;
  return typeof value === 'string' && value.trim() ? value : null;
}
