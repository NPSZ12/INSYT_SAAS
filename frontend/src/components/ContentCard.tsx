type ContentCardProps = {
  title?: string;
  children: React.ReactNode;
};

export default function ContentCard({
  title,
  children,
}: ContentCardProps) {
  return (
    <div className="bg-slate-800 rounded-2xl border border-slate-700 p-6">
      {title && (
        <h3 className="insyt-workspace text-2xl font-semibold mb-6 text-white">
          {title}
        </h3>
      )}

      {children}
    </div>
  );
}








