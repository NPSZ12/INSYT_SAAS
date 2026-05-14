type SectionGridProps = {
  children: React.ReactNode;
  cols?: 2 | 3 | 4;
};

export default function SectionGrid({
  children,
  cols = 2,
}: SectionGridProps) {
  const gridClass =
    cols === 4
      ? "grid grid-cols-4 gap-6"
      : cols === 3
      ? "grid grid-cols-3 gap-6"
      : "grid grid-cols-2 gap-6";

  return (
    <div className={gridClass}>
      {children}
    </div>
  );
}