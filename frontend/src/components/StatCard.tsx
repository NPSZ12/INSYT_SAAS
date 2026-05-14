type StatCardProps = {
  title: string;
  value: string;
};

export default function StatCard({
  title,
  value,
}: StatCardProps) {
  return (
    <div className="bg-slate-900 p-6 rounded-2xl border border-slate-800">
      <p className="text-slate-400 text-sm mb-2">
        {title}
      </p>

      <h3 className="text-4xl font-bold text-white">
        {value}
      </h3>
    </div>
  );
}