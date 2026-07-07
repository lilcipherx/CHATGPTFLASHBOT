/** Design-system on/off toggle. Replaces ad-hoc checkboxes for boolean settings. */
export function Switch({ checked, onChange, label, disabled, ariaLabel }: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: string;
  disabled?: boolean;
  ariaLabel?: string;  // FIX: AUDIT12-M13 - accessible name for icon-only switches
}) {
  return (
    <label className="switch" aria-disabled={disabled} style={disabled ? { opacity: .5, cursor: "default" } : undefined}>
      {/* FIX: AUDIT12-M13 - aria-label so screen readers announce the toggle's
          purpose even when the visible `label` prop is omitted (icon-only rows). */}
      <input type="checkbox" checked={checked} disabled={disabled}
        aria-label={ariaLabel ?? label}
        onChange={(e) => onChange(e.target.checked)} />
      <span className="track" aria-hidden="true"><span className="knob" /></span>
      {label && <span className="switch-label">{label}</span>}
    </label>
  );
}
