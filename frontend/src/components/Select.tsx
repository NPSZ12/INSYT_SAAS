type SelectProps = {
  children: React.ReactNode;
  value?: string;
  onChange?: (value: string) => void;
};

export default function Select({
  children,
  value,
  onChange,
}: SelectProps) {
  return (
    <select
      value={value}
      onChange={(event) => onChange?.(event.target.value)}
      className="w-full p-3 rounded-lg bg-slate-950 border border-slate-700 text-white focus:outline-none focus:border-teal-500"
    >
      {children}
    </select>
  );
}