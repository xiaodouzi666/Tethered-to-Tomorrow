import type { ExecutionMode } from '../../types/orchestrator';

const modes: Array<{ id: ExecutionMode; label: string }> = [
  { id: 'manual_step', label: 'Manual Step' },
  { id: 'manual_plan', label: 'Manual Plan' },
  { id: 'auto_step', label: 'Auto Step' }
];

export function ExecutionModeToggle({
  disabled,
  onChange,
  value
}: {
  disabled?: boolean;
  onChange: (mode: ExecutionMode) => void;
  value: ExecutionMode;
}) {
  return (
    <div className="orchestrator-toggle-row">
      {modes.map(mode => (
        <button
          className={mode.id === value ? 'selected' : ''}
          disabled={disabled}
          key={mode.id}
          onClick={() => onChange(mode.id)}
          type="button"
        >
          {mode.label}
        </button>
      ))}
    </div>
  );
}
