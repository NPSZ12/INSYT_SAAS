"use client";

export type SummaryOutlineItem = {
  id: string;
  title: string;
  citation: string;
  originalSummary: string;
  pageStart: number;
  pageEnd?: number | null;
};

type PdfOutlinePaneProps = {
  items: SummaryOutlineItem[];
  selectedTitle: string;
  onSelect: (item: SummaryOutlineItem) => void;
};

export default function PdfOutlinePane({
  items,
  selectedTitle,
  onSelect,
}: PdfOutlinePaneProps) {
  return (
    <aside className="h-full w-80 shrink-0 rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden">
      <div className="border-b border-slate-800 px-4 py-3">
        <h2 className="text-sm font-semibold text-white">
          PDF Outline
        </h2>
      </div>

      <div className="h-[calc(100%-49px)] overflow-y-auto">
        {items.length === 0 ? (
          <div className="px-4 py-4 text-sm text-slate-400">
            No outline items loaded.
          </div>
        ) : (
          items.map((item) => {
            const isSelected = item.title === selectedTitle;

            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelect(item)}
                className={`w-full border-b border-slate-800 px-4 py-3 text-left hover:bg-slate-800 ${
                  isSelected ? "bg-slate-800" : "bg-slate-900"
                }`}
              >
                <div className="text-sm font-semibold text-white">
                  {item.title}
                </div>

                <div className="mt-1 text-xs leading-snug text-slate-400">
                  {item.citation}
                </div>
              </button>
            );
          })
        )}
      </div>
    </aside>
  );
}