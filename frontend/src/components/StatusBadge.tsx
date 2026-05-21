type StatusBadgeProps = {
  children: React.ReactNode;
};

export default function StatusBadge({ children }: StatusBadgeProps) {
  return (
    <span className="text-xs bg-teal-500 text-slate-700 px-3 py-1 rounded-full">
      {children}
    </span>
  );
}








