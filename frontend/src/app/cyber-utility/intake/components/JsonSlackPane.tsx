"use client";

import StructuredIntakePaneShell, {
  StructuredIntakeGroup,
} from "./StructuredIntakePaneShell";


export type JsonSlackDataset = {
  docId: string;
  label: string;
  recordCount: number;
  secondaryLabel?: string;
};


type JsonSlackPaneProps = {
  recordCount?: number;
  packageCount?: number;

  datasets?: JsonSlackDataset[];

  channels?: StructuredIntakeGroup[];

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


export default function JsonSlackPane({
  recordCount = 0,
  packageCount = 0,

  datasets = [],
  channels = [],

  selectedDocIds = {},

  creatingHeaderSet = false,

  onToggleDocument,
  onSelectAll,
  onClearSelection,
  onCreateHeaderSet,
  onOpenDocument,
}: JsonSlackPaneProps) {

  const comingSoon =
    recordCount === 0 &&
    packageCount === 0 &&
    datasets.length === 0;


  const selectedCount =
    datasets.filter(
      (dataset) =>
        Boolean(
          selectedDocIds[
            dataset.docId
          ]
        )
    ).length;


  return (
    <StructuredIntakePaneShell
      title="JSON — Slack"
      subtitle="Slack exports preserved by workspace, channel, thread, message, user, and source relationship."
      recordCount={recordCount}
      packageCount={packageCount}
      groupLabel="Channels"
      groups={[]}
      comingSoon={comingSoon}
    >

      {!comingSoon ? (

        <div className="space-y-5">

          <div className="flex flex-wrap items-center justify-between gap-3">

            <div className="flex flex-wrap gap-2">

              <button
                type="button"
                onClick={
                  onSelectAll
                }
                className="rounded-lg border border-slate-700 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:border-sky-500 hover:text-sky-300"
              >
                Select All
              </button>

              <button
                type="button"
                onClick={
                  onClearSelection
                }
                className="rounded-lg border border-slate-700 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:border-sky-500 hover:text-sky-300"
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


          <div className="overflow-hidden rounded-xl border border-slate-800">

            <div className="overflow-x-auto">

              <table className="w-full text-left text-sm">

                <thead className="border-b border-slate-800 bg-slate-950/60 text-xs uppercase tracking-wide text-slate-500">

                  <tr>

                    <th className="px-4 py-3">
                      Select
                    </th>

                    <th className="px-4 py-3">
                      Slack Package
                    </th>

                    <th className="px-4 py-3">
                      Doc ID
                    </th>

                    <th className="px-4 py-3 text-right">
                      Messages
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
                            onChange={(
                              event
                            ) =>
                              onToggleDocument?.(
                                dataset.docId,
                                event.target.checked
                              )
                            }
                            className="h-4 w-4 rounded border-slate-600 bg-slate-950"
                          />

                        </td>


                        <td className="px-4 py-3">

                          <div className="font-medium text-slate-200">
                            {
                              dataset.label
                            }
                          </div>

                          {dataset.secondaryLabel ? (
                            <div className="mt-1 text-xs text-slate-500">
                              {
                                dataset.secondaryLabel
                              }
                            </div>
                          ) : null}

                        </td>


                        <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-slate-300">
                          {
                            dataset.docId
                          }
                        </td>


                        <td className="whitespace-nowrap px-4 py-3 text-right font-semibold text-slate-200">
                          {formatCount(
                            dataset.recordCount
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
                            Open
                          </button>

                        </td>

                      </tr>

                    )
                  )}

                </tbody>

              </table>

            </div>

          </div>


          {channels.length > 0 ? (

            <div className="cyber2-source-pane__groups">

              <div className="cyber2-source-pane__groups-title">
                Channels
              </div>

              {channels.map(
                (channel) => (

                  <div
                    key={
                      channel.id
                    }
                    className="cyber2-source-pane__group"
                  >

                    <div className="cyber2-source-pane__group-name">
                      {
                        channel.label
                      }
                    </div>

                    <div className="cyber2-source-pane__group-count">
                      {formatCount(
                        channel.recordCount
                      )}{" "}
                      message
                      {channel.recordCount === 1
                        ? ""
                        : "s"}
                    </div>

                  </div>

                )
              )}

            </div>

          ) : null}

        </div>

      ) : null}

    </StructuredIntakePaneShell>
  );
}