type StatusBadgeProps = {
  children: React.ReactNode;
};

export default function StatusBadge({ children }: StatusBadgeProps) {
  return (
    <span className="text-xs bg-teal-600 text-white px-3 py-1 rounded-full">
      {children}
    </span>
  );
}