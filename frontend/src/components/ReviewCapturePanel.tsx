"use client";

import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../lib/api";
import Button from "./Button";
import Input from "./Input";
import TextArea from "./TextArea";
import FormLabel from "./FormLabel";
import Checkbox from "./Checkbox";


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

type ReviewCapturePanelProps = {
  projectId: string;
  batchId: string;
  docId: string;
  fields: CaptureField[];
};

export default function ReviewCapturePanel({
  projectId,
  batchId,
  docId,
  fields,
}: ReviewCapturePanelProps) {
  const [values, setValues] = useState<Record<string, string | boolean>>({});
  const [linkedEntities, setLinkedEntities] = useState<LinkedEntity[]>([]);
  const [message, setMessage] = useState("");
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({});
  const [documentCoding, setDocumentCoding] = useState("");
  const [furtherReviewReason, setFurtherReviewReason] = useState("");

  useEffect(() => {
    apiGet(
      `/api/entities/document?project=${projectId}&batch=${batchId}&doc=${encodeURIComponent(docId)}`
    )
      .then((entities) => {
        setLinkedEntities(
          entities.map((entity: any, index: number) => ({
            id: entity.id ?? index + 1,
            docId: entity.doc_id,
            linked: entity.linked ?? true,
            values: entity.values,
          }))
        );
      })
      .catch(console.error);
  }, [projectId, batchId, docId]);

  function updateValue(label: string, value: string | boolean) {
    setValues((current) => ({
      ...current,
      [label]: value,
    }));
  }

  function toggleSection(section: string) {
    setOpenSections((current) => ({
      ...current,
      [section]: !current[section],
    }));
  }

  function clearValues() {
    setValues({});
  }

  function validateDocumentCoding() {
    if (!documentCoding) {
      setMessage("Document Coding selection is required.");
      return false;
    }

  if (
    documentCoding === "Not Responsive" &&
    linkedEntities.length > 0
  ) {
    setMessage(
      "Not Responsive documents cannot contain linked entities."
    );
    return false;
  }

  if (
    documentCoding === "Responsive" &&
    linkedEntities.length === 0
  ) {
    setMessage(
      "Responsive documents require at least one linked entity."
    );
    return false;
  }

  if (
    documentCoding === "Needs Further Review" &&
    !furtherReviewReason.trim()
  ) {
    setMessage(
      "Further Review reason is required."
    );
    return false;
  }

  return true;
}

  function handleLinkEntity() {
    if (documentCoding === "Not Responsive") {
      setMessage("Not Responsive documents cannot contain linked entities.");
      return;
    }

    const hasAnyValue = Object.values(values).some((value) => {
      if (typeof value === "boolean") {
        return value;
      }

      return String(value).trim() !== "";
    });

    if (!hasAnyValue) {
      setMessage("Add at least one captured value before linking an entity.");
      return;
    }

    const newEntity: LinkedEntity = {
      id: Date.now(),
      docId,
      linked: true,
      values,
    };

    setLinkedEntities((current) => [...current, newEntity]);

    apiPost("/api/review/save", {
      project_id: projectId,
      batch_id: batchId,
      doc_id: docId,
      values,
    })
      .then(() => {
        setMessage("Entity linked.");
        clearValues();
      })
      .catch(() => {
        setMessage("Entity linked locally, but backend save failed.");
        clearValues();
      });
  }

  function handleSaveNext() {
    if (!validateDocumentCoding()) {
      return;
    }

    apiPost("/api/review/save-next", {
      project_id: projectId,
      batch_id: batchId,
      doc_id: docId,
      document_coding: documentCoding,
      further_review_reason: furtherReviewReason,
      linked_entities: linkedEntities.map((entity) => entity.values),
    })
      .then(() => {
        setMessage("Document saved. Ready for next document.");
        setValues({});
        setDocumentCoding("");
        setFurtherReviewReason("");
        setLinkedEntities([]);
      })
      .catch(() => {
        setMessage("Save & Next failed.");
      });
  }

  function editLinkedEntity(entity: LinkedEntity) {
  setValues(entity.values);
  setMessage(`Editing linked entity ${entity.id}. Make corrections, then click Link Entity.`);
}

function unlinkEntity(entityId: number) {
  setLinkedEntities((current) =>
    current.map((entity) =>
      entity.id === entityId
        ? { ...entity, linked: false }
        : entity
    )
  );

  setMessage("Entity unlinked from this document but retained in Captured Entities.");
}

function deleteEntity(entityId: number) {
  const confirmed = window.confirm(
    "Confirm Deletion: This will permanently remove this linked entity from the project. Continue?"
  );

  if (!confirmed) {
    return;
  }

  apiPost("/api/entities/delete", {
    entity_id: entityId,
  })
    .then(() => {
      setLinkedEntities((current) =>
        current.filter((entity) => entity.id !== entityId)
      );

      setMessage("Entity deleted from the project.");
    })
    .catch(() => {
      setMessage("Delete failed.");
    });
}

  const groupedFields = fields.reduce<Record<string, CaptureField[]>>(
    (groups, field) => {
      const section = field.section || "Other";

      if (!groups[section]) {
        groups[section] = [];
      }

      groups[section].push(field);
      return groups;
    },
    {}
  );

  return (
    <aside className="bg-slate-900 border border-slate-800 rounded-2xl p-6 overflow-y-auto h-[82vh]">
      <h2 className="text-lg font-semibold mb-4 text-white">
        Capture Panel
      </h2>

      <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 mb-6">
        <h3 className="text-md font-semibold text-white mb-4">
          Document Coding Panel
        </h3>

        <div className="space-y-3">

          {[
            "Not Responsive",
            "Responsive",
            "Foreign Language",
            "Tech Issue",
            "Password Protected",
            "Needs Further Review",
          ].map((option) => (
            <label
              key={option}
              className="flex items-center gap-3 text-slate-300"
            >
              <input
                type="radio"
                name="documentCoding"
                checked={documentCoding === option}
                onChange={() => setDocumentCoding(option)}
                className="accent-sky-600"
              />

              <span>{option}</span>
            </label>
          ))}

          {documentCoding === "Needs Further Review" && (
            <div className="mt-4">
              <FormLabel>
                Further Review Reason
              </FormLabel>

              <TextArea
                rows={3}
                value={furtherReviewReason}
                onChange={setFurtherReviewReason}
              />
            </div>
          )}

        </div>
      </div>

      <div className="space-y-4">
        {Object.entries(groupedFields).map(([section, sectionFields]) => {
          const isOpen = openSections[section] ?? false;

          return (
            <div
              key={section}
              className="bg-slate-950 border border-slate-800 rounded-xl overflow-hidden max-h-[60vh] flex flex-col"
            >
              <button
                type="button"
                onClick={() => toggleSection(section)}
                className="sticky top-0 z-20 w-full flex items-center justify-between px-4 py-3 text-left bg-lime-50 hover:bg-lime-50 border border-sky-700 transition border-b border-slate-800"
              >
              
                <span className="font-semibold text-white">
                  {section}
                </span>

                <span className="text-white text-lg font-bold">
                  {isOpen ? "−" : "+"}
                </span>
              </button>

              {isOpen && (
                <div className="p-4 border-t border-slate-800 overflow-y-auto">
                  {sectionFields.map((field) => (
                    <div key={field.label} className="mb-4">
                      {field.type === "checkbox" ? (
                        <>
                          <Checkbox
                            label={field.label}
                            checked={Boolean(values[field.label])}
                            onChange={(checked) =>
                              updateValue(field.label, checked)
                            }
                          />

                          {field.notes && (
                            <p className="text-xs text-slate-500 -mt-2 mb-3">
                              {field.notes}
                            </p>
                          )}
                        </>
                      ) : field.type === "textarea" ? (
                        <>
                          <FormLabel>{field.label}</FormLabel>

                          <TextArea
                            rows={1}
                            value={String(values[field.label] ?? "")}
                            onChange={(value) =>
                              updateValue(field.label, value)
                            }
                          />

                          {field.notes && (
                            <p className="text-xs text-slate-500 mt-1">
                              {field.notes}
                            </p>
                          )}
                        </>
                      ) : (
                        <>
                          <FormLabel>{field.label}</FormLabel>

                          <Input
                            value={String(values[field.label] ?? "")}
                            onChange={(value) =>
                              updateValue(field.label, value)
                            }
                          />

                          {field.notes && (
                            <p className="text-xs text-slate-500 mt-1">
                              {field.notes}
                            </p>
                          )}
                        </>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-6">
        <Button fullWidth onClick={handleLinkEntity}>
          Link Entity
        </Button>
      </div>

      <div className="mt-3">
        <Button fullWidth variant="secondary" onClick={handleSaveNext}>
          Save & Next Document
        </Button>
      </div>    

      {message && (
        <p className="text-sm text-slate-400 mt-4">
          {message}
        </p>
      )}

      <div className="mt-8 border-t border-slate-800 pt-6">
        <h3 className="text-lg font-semibold text-white mb-4">
          Linked Entities
        </h3>

        {linkedEntities.length === 0 ? (
          <p className="text-sm text-slate-500">
            No entities linked for this document yet.
          </p>
        ) : (
          <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-auto">
            <table className="min-w-max w-full text-xs">
              <thead className="bg-slate-900 text-slate-400">
                <tr>
                  <th className="p-3 text-left sticky left-0 bg-slate-900 z-20">
                    Actions
                  </th>

                  <th className="p-3 text-left sticky left-[150px] bg-slate-900 z-20 border-l border-slate-800">
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
                    <td className="p-2 sticky left-0 bg-slate-950 z-10">
                      <div className="flex gap-1">
                        <button
                          type="button"
                          onClick={() => editLinkedEntity(entity)}
                          className="text-xs px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200"
                        >
                          Edit
                        </button>

                        <button
                          type="button"
                          onClick={() => unlinkEntity(entity.id)}
                          className="text-xs px-2 py-1 rounded bg-yellow-700 hover:bg-yellow-600 text-white"
                        >
                          Unlink
                        </button>

                        <button
                          type="button"
                          onClick={() => deleteEntity(entity.id)}
                          className="text-xs px-2 py-1 rounded bg-red-700 hover:bg-red-600 text-white"
                        >
                          Delete
                        </button>
                      </div>
                    </td>

                    <td className="p-3 text-slate-400 sticky left-[150px] bg-slate-950 z-10 border-l border-slate-800">
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
          </div>
        )}
      </div>
    </aside>
  );
}








