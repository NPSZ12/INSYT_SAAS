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
};

export default function ReviewHeader({
  project,
  batch,
  docId,
  isFirstDoc = false,
  isLastDoc = false,
  docPositionLabel = "",
  onFirstDoc,
  onPreviousDoc,
  onNextDoc,
  onLastDoc,
}: ReviewHeaderProps) {
  return (
    <header className="h-16 bg-slate-900 border-b border-slate-800 px-6 flex items-center justify-between">
      <div>
        

        <p className="text-xs text-slate-400">
          {project} / {batch} / {docId}
        </p>
      </div>

      <div className="flex items-center gap-3">
        {!isFirstDoc && (
          <Button
            variant="secondary"
            onClick={onFirstDoc}
          >
            First Doc
          </Button>
        )}

        {!isFirstDoc && (
          <Button
            variant="secondary"
            onClick={onPreviousDoc}
          >
            Previous Doc
          </Button>
        )}

        {docPositionLabel && (
          <span className="text-sm text-slate-300 whitespace-nowrap">
            {docPositionLabel}
          </span>
        )}

        {!isLastDoc && (
          <Button
            variant="secondary"
            onClick={onNextDoc}
          >
            Next Doc
          </Button>
        )}

        {!isLastDoc && (
          <Button
            variant="secondary"
            onClick={onLastDoc}
          >
            Last Doc
          </Button>
        )}
      </div>
    </header>
  );
}