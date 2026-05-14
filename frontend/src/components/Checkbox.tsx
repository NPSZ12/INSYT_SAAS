type CheckboxProps = {
  label: string;
  defaultChecked?: boolean;
  checked?: boolean;
  onChange?: (checked: boolean) => void;
};

export default function Checkbox({
  label,
  defaultChecked = false,
  checked,
  onChange,
}: CheckboxProps) {
  return (
    <label className="flex items-center gap-3 mb-4 text-slate-300">
      <input
        type="checkbox"
        defaultChecked={checked === undefined ? defaultChecked : undefined}
        checked={checked}
        onChange={(event) => onChange?.(event.target.checked)}
        className="accent-teal-600"
      />
      <span>{label}</span>
    </label>
  );
}