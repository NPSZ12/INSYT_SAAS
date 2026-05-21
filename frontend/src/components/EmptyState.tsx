type EmptyStateProps = {
  title: string;
  message: string;
};

export default function EmptyState({
  title,
  message,
}: EmptyStateProps) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-10 text-center">
      <h3 className="text-2xl font-semibold text-white mb-2">
        {title}
      </h3>

      <p className="text-slate-400">
        {message}
      </p>
    </div>
  );
}








