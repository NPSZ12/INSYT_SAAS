"use client";

export type PdfOutlineItem = {
  id: string;
  title: string;
  linkedText?: string;
  citation?: string;
  page?: number;
  pageStart?: number;
  pageEnd?: number | null;
  y?: number;
  originalSummary?: string;
  qcSummary?: string;
};

export type SummaryOutlineItem = PdfOutlineItem;

type PdfOutlinePaneProps = {
  projectId?: string;

  outlineItems?: PdfOutlineItem[];
  originalOutlineItems?: string[];
  updatedOutlineItems?: string[];

  selectedOutlineItemId?: string;

  onSelectHyperlink?: (text: string) => void;
  onSelectOutlineItem?: (item: PdfOutlineItem) => void;

  /**
   * Backward-compatible props.
   * These keep older review pages from breaking while we migrate.
   */
  items?: PdfOutlineItem[];
  selectedTitle?: string;
  onSelect?: (item: PdfOutlineItem) => void;
};

export default function PdfOutlinePane({
  projectId,
  outlineItems,
  originalOutlineItems = [],
  updatedOutlineItems = [],
  selectedOutlineItemId,
  onSelectHyperlink,
  onSelectOutlineItem,

  items,
  selectedTitle,
  onSelect,
}: PdfOutlinePaneProps) {
  const resolvedOutlineItems = outlineItems ?? items ?? [];

  function getItemPage(item: PdfOutlineItem) {
    return item.page ?? item.pageStart;
  }

  function handleSelectItem(item: PdfOutlineItem) {
    const normalizedItem: PdfOutlineItem = {
      ...item,
      page: item.page ?? item.pageStart,
      qcSummary: item.qcSummary || item.originalSummary || "",
    };

    onSelectOutlineItem?.(normalizedItem);
    onSelect?.(normalizedItem);

    onSelectHyperlink?.(
      normalizedItem.linkedText || normalizedItem.title
    );
  }

  return (
    <div className="h-full flex flex-col bg-slate-950">
      <div className="shrink-0 px-5 py-4 border-b border-slate-800 bg-slate-950">
        <h2 className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
          PDF Outline
        </h2>

        {projectId && (
          <p className="mt-2 text-xs text-sky-400 font-semibold truncate">
            {projectId.replaceAll("_", " ")}
          </p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        <section>
          <div className="text-xs uppercase tracking-[0.14em] text-slate-500 mb-2">
            Table of Contents
          </div>

          {resolvedOutlineItems.length === 0 ? (
            <p className="text-sm text-slate-500">
              No PDF table of contents loaded.
            </p>
          ) : (
            <div className="space-y-1">
              {resolvedOutlineItems.map((item) => {
                const itemPage = getItemPage(item);

                const isSelected =
                  item.id === selectedOutlineItemId ||
                  item.title === selectedTitle;

                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => handleSelectItem(item)}
                    className={[
                      "block w-full text-left rounded-lg px-3 py-2 text-sm transition",
                      isSelected
                        ? "bg-sky-950/60 text-sky-300 ring-1 ring-sky-700/60"
                        : "text-sky-400 hover:bg-slate-900 hover:text-sky-300",
                    ].join(" ")}
                  >
                    <div className="font-medium">
                      {itemPage ? `p. ${itemPage} — ` : ""}
                      {item.title}
                    </div>

                    {item.citation && (
                      <div className="mt-1 text-[11px] leading-4 text-slate-500">
                        {item.citation}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </section>

        <section className="border-t border-slate-800 pt-4">
          <div className="text-xs uppercase tracking-[0.14em] text-slate-500 mb-2">
            Original Summary Outline
          </div>

          {originalOutlineItems.length === 0 ? (
            <p className="text-sm text-slate-500">
              Select a table of contents item to load original summary text.
            </p>
          ) : (
            <div className="space-y-1 text-sm text-slate-300">
              {originalOutlineItems.map((item, index) => (
                <div key={`${item}-${index}`}>
                  {index + 1}. {item}
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="border-t border-slate-800 pt-4">
          <div className="text-xs uppercase tracking-[0.14em] text-slate-500 mb-2">
            QC Summary Outline
          </div>

          {updatedOutlineItems.length === 0 ? (
            <p className="text-sm text-slate-500">
              QC edits will generate the updated outline.
            </p>
          ) : (
            <div className="space-y-1 text-sm text-slate-300">
              {updatedOutlineItems.map((item, index) => (
                <div key={`${item}-${index}`}>
                  {index + 1}. {item}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}