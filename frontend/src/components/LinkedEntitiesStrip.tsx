"use client";

type CaptureField = {
  section: string;
  label: string;
  type: string;
  format?: string;
  notes?: string;
};

type LinkedEntity = {
  id: number;
  docId: string;
  linked: boolean;
  values: Record<string, string | boolean>;
};

type LinkedEntitiesStripProps = {
  fields: CaptureField[];
  linkedEntities: LinkedEntity[];
  onEdit: (entity: LinkedEntity) => void;
  onUnlink: (entityId: number) => void;
  onDelete: (entityId: number) => void;
};

export default function LinkedEntitiesStrip({
  fields,
  linkedEntities,
  onEdit,
  onUnlink,
  onDelete,
}: LinkedEntitiesStripProps) {
  return (
    <section className="h-64 bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden flex flex-col">
      <div className="shrink-0 px-5 py-3 border-b border-slate-800 bg-slate-950">
        <h3 className="text-lg font-semibold text-white">
          Linked Entities
        </h3>
      </div>

      <div className="flex-1 overflow-auto">
        {linkedEntities.length === 0 ? (
          <p className="p-5 text-sm text-slate-500">
            No entities linked for this document yet.
          </p>
        ) : (
          <table className="min-w-max w-full text-xs">
            <thead className="bg-slate-900 text-slate-400 sticky top-0 z-20">
              <tr>
                <th className="p-3 text-left sticky left-0 bg-slate-900 z-30">
                  Actions
                </th>

                <th className="p-3 text-left sticky left-[150px] bg-slate-900 z-30 border-l border-slate-800">
                  #
                </th>

                {fields.map((field) => (
                  <th
                    key={field.label}
                    className="p-3 text-left whitespace-nowrap border-l border-slate-800"
                  >
                    {field.label}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody>
              {linkedEntities.map((entity, index) => (
                <tr
                  key={entity.id}
                  className="border-t border-slate-800"
                >
                  <td className="p-2 sticky left-0 bg-slate-950 z-20">
                    <div className="flex gap-1">
                      <button
                        type="button"
                        onClick={() => onEdit(entity)}
                        className="text-xs px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200"
                      >
                        Edit
                      </button>

                      <button
                        type="button"
                        onClick={() => onUnlink(entity.id)}
                        className="text-xs px-2 py-1 rounded bg-yellow-700 hover:bg-yellow-600 text-white"
                      >
                        Unlink
                      </button>

                      <button
                        type="button"
                        onClick={() => onDelete(entity.id)}
                        className="text-xs px-2 py-1 rounded bg-red-700 hover:bg-red-600 text-white"
                      >
                        Delete
                      </button>
                    </div>
                  </td>

                  <td className="p-3 text-slate-400 sticky left-[150px] bg-slate-950 z-20 border-l border-slate-800">
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
                        className="p-3 text-slate-300 border-l border-slate-800 whitespace-nowrap"
                      >
                        {typeof value === "boolean"
                          ? value
                            ? "Yes"
                            : ""
                          : String(value ?? "")}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}