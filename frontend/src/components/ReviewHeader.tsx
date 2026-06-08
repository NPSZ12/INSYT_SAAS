"use client";

import Button from "./Button";

type ReviewHeaderProps = {
  project: string;
  batch: string;
  docId: string;
  isFirstDoc?: boolean;
  isLastDoc?: boolean;
  docPositionLabel?: string;
  onFirstDoc?: () => void;
  onPreviousDoc?: () => void;
  onNextDoc?: () => void;
  onLastDoc?: () => void;
  currentDocIndex?: number;
  batchDocCount?: number;
};

export default function ReviewHeader({
  project,
  batch,
  docId,
  docPositionLabel = "",
  currentDocIndex,
  batchDocCount,
  onFirstDoc,
  onPreviousDoc,
  onNextDoc,
  onLastDoc,
}: ReviewHeaderProps) {
  const positionLabel =
    docPositionLabel ||
    (
      typeof currentDocIndex === "number" &&
      typeof batchDocCount === "number" &&
      currentDocIndex >= 0 &&
      batchDocCount > 0
        ? `Doc ${currentDocIndex + 1} of ${batchDocCount}`
        : "Doc - of -"
    );

  return (
    <header className="h-16 bg-slate-900 border-b border-slate-800 px-6 flex items-center justify-between gap-4">
      <div className="min-w-0">
        <p className="text-xs text-slate-400 truncate">
          {project} / {batch} / {docId}
        </p>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        <Button variant="secondary" onClick={onFirstDoc}>
          First Doc
        </Button>

        <Button variant="secondary" onClick={onPreviousDoc}>
          Previous Doc
        </Button>

        <span className="min-w-28 text-center text-sm text-slate-300 whitespace-nowrap">
          {positionLabel}
        </span>

        <Button variant="secondary" onClick={onNextDoc}>
          Next Doc
        </Button>

        <Button variant="secondary" onClick={onLastDoc}>
          Last Doc
        </Button>
      </div>
    </header>
  );
}