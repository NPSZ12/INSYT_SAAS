type StatCardProps = {
  title: string;
  value: string | number;
  className?: string;
};

export default function StatCard({
  title,
  value,
  className = "",
}: StatCardProps) {
  return (
    <div className={`insyt-card p-6 ${className}`}>
      <p className="mb-2 text-sm font-medium insyt-text-muted">
        {title}
      </p>

      <h3 className="text-4xl font-bold insyt-text-primary">
        {value}
      </h3>
    </div>
  );
}