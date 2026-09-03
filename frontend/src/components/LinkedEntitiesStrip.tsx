"use client";

type CaptureField = {
  section: string;
  label: string;
  type: string;
  format?: string;
  notes?: string;
};

type LinkedEntity = {
  id: number | string;
  ucid?: string;
  UCID?: string;
  docId: string;
  linked: boolean;
  values: Record<string, string | boolean>;
};

type LinkedEntitiesStripProps = {
  fields: CaptureField[];
  linkedEntities: LinkedEntity[];
  onEdit: (entity: LinkedEntity) => void;
  onUnlink: (entityId: number | string) => void;
  onDelete: (entityId: number | string) => void;
};

export default function LinkedEntitiesStrip({
  fields,
  linkedEntities,
  onEdit,
  onUnlink,
  onDelete,
}: LinkedEntitiesStripProps) {
  return (
    <section className="flex h-64 flex-col overflow-hidden rounded-2xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)]">
      <div className="shrink-0 border-b border-[var(--insyt-border)] bg-[var(--insyt-surface-2)] px-5 py-3">
        <h3 className="insyt-section-title text-lg text-[var(--insyt-text-primary)]">
          Linked Entities
        </h3>
      </div>

      <div className="flex-1 overflow-auto">
        {linkedEntities.length === 0 ? (
          <p className="p-5 text-sm text-[var(--insyt-text-muted)]">
            No entities linked for this document yet.
          </p>
        ) : (
          <table className="min-w-max w-full text-xs">
            <thead className="sticky top-0 z-20 bg-[var(--insyt-surface-2)] text-[var(--insyt-text-muted)]">
              <tr>
                <th className="sticky left-0 z-30 bg-[var(--insyt-surface-2)] p-3 text-left">
                  Actions
                </th>

                <th className="sticky left-[150px] z-30 border-l border-[var(--insyt-border)] bg-[var(--insyt-surface-2)] p-3 text-left">
                  #
                </th>

                {fields.map((field) => (
                  <th
                    key={field.label}
                    className="whitespace-nowrap border-l border-[var(--insyt-border)] p-3 text-left"
                  >
                    {field.label}
                  </th>
                ))}

                <th className="whitespace-nowrap border-l border-[var(--insyt-border)] p-3 text-left">
                  UCID
                </th>
              </tr>
            </thead>

            <tbody>
              {linkedEntities.map((entity, index) => (
                <tr
                  key={entity.id}
                  className="border-t border-[var(--insyt-border)]"
                >
                  <td className="sticky left-0 z-20 bg-[var(--insyt-surface-1)] p-2">
                    <div className="flex gap-1">
                      <button
                        type="button"
                        onClick={() => onEdit(entity)}
                        className="rounded-xl border border-sky-500/50 bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-500 transition hover:bg-sky-500/20"
                      >
                        Edit
                      </button>

                      <button
                        type="button"
                        onClick={() => onUnlink(entity.id)}
                        className="rounded-xl border border-orange-500/50 bg-orange-500/10 px-3 py-1.5 text-xs font-semibold text-orange-600 transition hover:bg-orange-500/20"
                      >
                        Unlink
                      </button>

                      <button
                        type="button"
                        onClick={() => onDelete(entity.id)}
                        className="rounded-xl border border-red-500/50 bg-red-500/10 px-3 py-1.5 text-xs font-semibold text-red-500 transition hover:bg-red-500/20"
                      >
                        Delete
                      </button>
                    </div>
                  </td>

                  <td className="sticky left-[150px] z-20 border-l border-[var(--insyt-border)] bg-[var(--insyt-surface-1)] p-3 text-[var(--insyt-text-muted)]">
                    {index + 1}

                    {!entity.linked && (
                      <span className="ml-2 text-yellow-400">
                        Unlinked
                      </span>
                    )}
                  </td>

                  {fields.map((field) => {
                    const value = entity.values[field.label];

                    return (
                      <td
                        key={field.label}
                        className="whitespace-nowrap border-l border-[var(--insyt-border)] p-3 text-[var(--insyt-text-secondary)]"
                      >
                        {typeof value === "boolean"
                          ? value
                            ? "Yes"
                            : ""
                          : String(value ?? "")}
                      </td>
                    );
                  })}

                  <td className="whitespace-nowrap border-l border-[var(--insyt-border)] p-3 text-[var(--insyt-text-muted)]">
                    {entity.ucid ||
                      entity.UCID ||
                      entity.values.UCID ||
                      ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}