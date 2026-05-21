"use client";

import { useState } from "react";
import Button from "./Button";

type ReviewHeaderProps = {
  project: string;
  batch: string;
  docId: string;
};

export default function ReviewHeader({
  project,
  batch,
  docId,
}: ReviewHeaderProps) {
  const [message, setMessage] = useState("");

  function handlePreviousDoc() {
    setMessage(`Loading previous document before ${docId}...`);
  }

  function handleSaveNext() {
    setMessage(`Saved ${docId}. Loading next document...`);
  }

  function handleNextDoc() {
    setMessage(`Loading next document after ${docId}...`);
  }

  return (
    <header className="h-16 bg-slate-900 border-b border-slate-800 px-6 flex items-center justify-between">
      <div>
        <h1 className="text-xl font-bold">
          INSYT Review
        </h1>

        <p className="text-xs text-slate-400">
          {project} / {batch} / {docId}
        </p>

        {message && (
          <p className="text-xs text-sky-400 mt-1">
            {message}
          </p>
        )}
      </div>

      <div className="flex items-center gap-3">
        <Button
          variant="secondary"
          onClick={handlePreviousDoc}
        >
          Previous Doc
        </Button>

        <Button onClick={handleSaveNext}>
          Save & Next
        </Button>

        <Button
          variant="secondary"
          onClick={handleNextDoc}
        >
          Next Doc
        </Button>
      </div>
    </header>
  );
}








