type FormLabelProps = {
  children: React.ReactNode;
};

export default function FormLabel({ children }: FormLabelProps) {
  return (
    <label className="block text-sm text-slate-400 mb-2">
      {children}
    </label>
  );
}