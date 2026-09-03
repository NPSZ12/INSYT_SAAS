type SelectProps = {
  children: React.ReactNode;
  value?: string;
  onChange?: (value: string) => void;
  disabled?: boolean;
  className?: string;
};

export default function Select({
  children,
  value,
  onChange,
  disabled = false,
  className = "",
}: SelectProps) {
  return (
    <select
      value={value}
      onChange={(event) => onChange?.(event.target.value)}
      disabled={disabled}
      className={`insyt-control insyt-select ${className}`}
    >
      {children}
    </select>
  );
}