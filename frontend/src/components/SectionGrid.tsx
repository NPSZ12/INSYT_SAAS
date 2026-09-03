type SectionGridProps = {
  children: React.ReactNode;
  cols?: 2 | 3 | 4;
  className?: string;
};

export default function SectionGrid({
  children,
  cols = 2,
  className = "",
}: SectionGridProps) {
  const gridClass =
    cols === 4
      ? "insyt-section-grid insyt-section-grid-4"
      : cols === 3
        ? "insyt-section-grid insyt-section-grid-3"
        : "insyt-section-grid insyt-section-grid-2";

  return (
    <div className={`${gridClass} ${className}`}>
      {children}
    </div>
  );
}