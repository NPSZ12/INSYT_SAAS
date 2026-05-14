type TextAreaProps = {
  placeholder?: string;
  rows?: number;
  value?: string;
  onChange?: (value: string) => void;
};

export default function TextArea({
  placeholder,
  rows = 4,
  value,
  onChange,
}: TextAreaProps) {
  return (
    <textarea
      rows={rows}
      value={value}
      onChange={(event) => onChange?.(event.target.value)}
      placeholder={placeholder}
      className="w-full p-3 rounded-lg bg-slate-950 border border-slate-700 text-white placeholder:text-slate-500 focus:outline-none focus:border-teal-500 resize-none overflow-y-auto"
    />
  );
}