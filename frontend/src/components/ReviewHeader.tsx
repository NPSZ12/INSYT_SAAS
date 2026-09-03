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
  hideDocNavigation?: boolean;
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
  hideDocNavigation = false,
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
    <header className="flex h-16 items-center justify-between gap-4 border-b border-[var(--insyt-border)] bg-[var(--insyt-surface-1)] px-6">
      <div className="min-w-0">
        <p className="truncate text-xs text-[var(--insyt-text-muted)]">
          {project} / {batch} / {docId}
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-3">
        {!hideDocNavigation && (
          <>
            <Button variant="secondary" onClick={onFirstDoc}>
              First Doc
            </Button>

            <Button variant="secondary" onClick={onPreviousDoc}>
              Previous Doc
            </Button>
          </>
        )}

        <span className="min-w-28 whitespace-nowrap text-center text-sm font-medium text-[var(--insyt-text-secondary)]">
          {positionLabel}
        </span>

        {!hideDocNavigation && (
          <>
            <Button variant="secondary" onClick={onNextDoc}>
              Next Doc
            </Button>

            <Button variant="secondary" onClick={onLastDoc}>
              Last Doc
            </Button>
          </>
        )}
      </div>
    </header>
  );
}