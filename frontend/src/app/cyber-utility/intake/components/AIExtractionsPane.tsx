"use client";

import StructuredIntakePaneShell from "./StructuredIntakePaneShell";

export type AIExtractionDataset = {
  docId: string;
  processingSetId: string;
  sourceJobId?: string;
  sourceDocumentCount: number;
  aiEntityCount: number;
  entityTypes?: string[];
  filename?: string;
  assigned?: boolean;
};

type AIExtractionsPaneProps = {
  datasets?: AIExtractionDataset[];

  selectedDocIds?: Record<
    string,
    boolean
  >;

  creatingHeaderSet?: boolean;

  onToggleDocument?: (
    docId: string,
    selected: boolean
  ) => void;

  onSelectAll?: () => void;
  onClearSelection?: () => void;

  onCreateHeaderSet?: () => void;

  onOpenDocument?: (
    docId: string
  ) => void;
};

function formatCount(
  value?: number
) {
  return Number(
    value || 0
  ).toLocaleString();
}

export default function AIExtractionsPane({
  datasets = [],
  selectedDocIds = {},
  creatingHeaderSet = false,
  onToggleDocument,
  onSelectAll,
  onClearSelection,
  onCreateHeaderSet,
  onOpenDocument,
}: AIExtractionsPaneProps) {

  const selectedCount =
    datasets.filter(
      (dataset) =>
        Boolean(
          selectedDocIds[
            dataset.docId
          ]
        )
    ).length;

  const entityCount =
    datasets.reduce(
      (
        total,
        dataset
      ) =>
        total +
        Math.max(
          0,
          Number(
            dataset.aiEntityCount ||
            0
          )
        ),
      0
    );

  return (
    <StructuredIntakePaneShell
      title="AI-Extractions"
      subtitle="AI-grouped entities generated from existing Processing Sets and Data Element Detection results."
      recordCount={entityCount}
      packageCount={datasets.length}
      groupLabel="Processing Sets"
      groups={[]}
      comingSoon={false}
    >

      <div className="space-y-4">

        <div className="flex flex-wrap items-center justify-between gap-3">

          <div className="flex flex-wrap gap-2">

            <button
              type="button"
              onClick={
                onSelectAll
              }
              disabled={
                datasets.length === 0
              }
              className="rounded-lg border border-slate-700 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:border-sky-500 hover:text-sky-300 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Select All
            </button>

            <button
              type="button"
              onClick={
                onClearSelection
              }
              disabled={
                selectedCount === 0
              }
              className="rounded-lg border border-slate-700 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:border-sky-500 hover:text-sky-300 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Clear Selection
            </button>

          </div>

          <button
            type="button"
            onClick={
              onCreateHeaderSet
            }
            disabled={
              selectedCount === 0 ||
              creatingHeaderSet
            }
            className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {creatingHeaderSet
              ? "Creating..."
              : `Create Header Set${
                  selectedCount
                    ? ` (${selectedCount})`
                    : ""
                }`}
          </button>

        </div>

        {datasets.length === 0 ? (

          <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/30 px-6 py-10 text-center">

            <div className="text-sm font-medium text-slate-300">
              No AI Extraction sets are currently available.
            </div>

            <div className="mt-2 text-xs text-slate-500">
              Completed AI Extraction Processing Sets will appear here automatically.
            </div>

          </div>

        ) : (

          <div className="overflow-hidden rounded-xl border border-slate-800">

            <div className="overflow-x-auto">

              <table className="min-w-[1100px] w-full text-left text-sm">

                <thead className="border-b border-slate-800 bg-slate-950/60 text-xs uppercase tracking-wide text-slate-500">

                  <tr>

                    <th className="px-4 py-3">
                      Select
                    </th>

                    <th className="px-4 py-3">
                      Processing Set
                    </th>

                    <th className="px-4 py-3">
                      Source Job
                    </th>

                    <th className="px-4 py-3 text-right">
                      Source Docs
                    </th>

                    <th className="px-4 py-3 text-right">
                      AI Entities
                    </th>

                    <th className="px-4 py-3">
                      Detected Types
                    </th>

                    <th className="px-4 py-3">
                      Status
                    </th>

                    <th className="px-4 py-3">
                      Action
                    </th>

                  </tr>

                </thead>

                <tbody className="divide-y divide-slate-800">

                  {datasets.map(
                    (dataset) => (

                      <tr
                        key={
                          dataset.docId
                        }
                        className="bg-slate-950/20 hover:bg-slate-900/70"
                      >

                        <td className="px-4 py-3">

                          <input
                            type="checkbox"
                            checked={
                              Boolean(
                                selectedDocIds[
                                  dataset.docId
                                ]
                              )
                            }
                            disabled={
                              Boolean(
                                dataset.assigned
                              )
                            }
                            onChange={(
                              event
                            ) =>
                              onToggleDocument?.(
                                dataset.docId,
                                event.target.checked
                              )
                            }
                            className="h-4 w-4 rounded border-slate-600 bg-slate-950 disabled:cursor-not-allowed disabled:opacity-30"
                          />

                        </td>

                        <td className="px-4 py-3">

                          <div className="font-mono text-xs text-slate-200">
                            {
                              dataset.processingSetId
                            }
                          </div>

                          {dataset.filename ? (
                            <div className="mt-1 text-xs text-slate-500">
                              {
                                dataset.filename
                              }
                            </div>
                          ) : null}

                        </td>

                        <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-slate-400">
                          {
                            dataset.sourceJobId ||
                            "—"
                          }
                        </td>

                        <td className="whitespace-nowrap px-4 py-3 text-right font-semibold text-slate-200">
                          {formatCount(
                            dataset.sourceDocumentCount
                          )}
                        </td>

                        <td className="whitespace-nowrap px-4 py-3 text-right font-semibold text-slate-200">
                          {formatCount(
                            dataset.aiEntityCount
                          )}
                        </td>

                        <td className="max-w-[360px] px-4 py-3">

                          <div className="flex flex-wrap gap-1.5">

                            {(
                              dataset.entityTypes ||
                              []
                            ).map(
                              (
                                entityType
                              ) => (
                                <span
                                  key={
                                    entityType
                                  }
                                  className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-300"
                                >
                                  {
                                    entityType
                                  }
                                </span>
                              )
                            )}

                          </div>

                        </td>

                        <td className="px-4 py-3">

                          {dataset.assigned ? (

                            <span className="text-xs font-medium text-violet-300">
                              Assigned
                            </span>

                          ) : (

                            <span className="text-xs font-medium text-emerald-300">
                              Ready
                            </span>

                          )}

                        </td>

                        <td className="px-4 py-3">

                          <button
                            type="button"
                            onClick={() =>
                              onOpenDocument?.(
                                dataset.docId
                              )
                            }
                            className="text-sm font-semibold text-sky-400 underline transition-colors hover:text-sky-300"
                          >
                            Open CSV
                          </button>

                        </td>

                      </tr>

                    )
                  )}

                </tbody>

              </table>

            </div>

          </div>

        )}

      </div>

    </StructuredIntakePaneShell>
  );
}