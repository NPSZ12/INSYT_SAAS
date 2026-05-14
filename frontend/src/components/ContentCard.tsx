type ContentCardProps = {
  title: string;
  children: React.ReactNode;
};

export default function ContentCard({
  title,
  children,
}: ContentCardProps) {
  return (
    <div className="bg-slate-900 rounded-2xl border border-slate-800 p-6">
      <h3 className="text-2xl font-semibold mb-6 text-white">
        {title}
      </h3>

      {children}
    </div>
  );
}