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

  const [message, setMessage] = useState("");

  const [openSections, setOpenSections] =
    useState<Record<string, boolean>>({});

  const [documentCoding, setDocumentCoding] =
    useState("");

  const [furtherReviewReason, setFurtherReviewReason] =
    useState("");

  useEffect(() => {
    const initialOpenState: Record<string, boolean> = {};

    fields.forEach((field) => {
      const section = field.section || "General";

      initialOpenState[section] = false;
    });

    setOpenSections(initialOpenState);
  }, [fields]);

  function normalizeFieldType(field: CaptureField) {
    const typeText =
      `${field.type || ""} ${field.format || ""}`.toLowerCase();

    if (
      typeText.includes("tag") ||
      typeText.includes("checkbox") ||
      typeText.includes("boolean") ||
      typeText.includes("yes/no")
    ) {
      return "tag";
    }

    if (
      typeText.includes("textarea") ||
      typeText.includes("long text")
    ) {
      return "textarea";
    }

    return "text";
  }

  function updateValue(
    label: string,
    value: string | boolean
  ) {
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

  function validateDocumentCoding() {
    if (!documentCoding) {
      setMessage(
        "Document Coding selection is required."
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

  function handleSaveNext() {
    if (!validateDocumentCoding()) {
      return;
    }

    apiPost("/api/review/save-next", {
      project_id: projectId,
      batch_id: batchId,
      doc_id: docId,
      values,
      document_coding: documentCoding,
      further_review_reason: furtherReviewReason,
    })
      .then(() => {
        setMessage(
          "Document saved. Ready for next document."
        );

        setValues({});
        setDocumentCoding("");
        setFurtherReviewReason("");
      })
      .catch(() => {
        setMessage("Save & Next failed.");
      });
  }

  const groupedFields =
    fields.reduce<Record<string, CaptureField[]>>(
      (groups, field) => {
        const section = field.section || "General";

        if (!groups[section]) {
          groups[section] = [];
        }

        groups[section].push(field);

        return groups;
      },
      {}
    );

  return (
    <aside className="bg-slate-900 border border-slate-800 rounded-2xl p-6 overflow-y-auto h-full">
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
                onChange={() =>
                  setDocumentCoding(option)
                }
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
        {Object.entries(groupedFields).length === 0 ? (
          <p className="text-sm text-slate-500">
            No protocol capture fields loaded.
          </p>
        ) : (
          Object.entries(groupedFields).map(
            ([section, sectionFields]) => {
              const isOpen =
                openSections[section] ?? false;

              return (
                <div
                  key={section}
                  className="bg-slate-950 border border-slate-800 rounded-xl overflow-hidden"
                >
                  <button
                    type="button"
                    onClick={() =>
                      toggleSection(section)
                    }
                    className="w-full flex items-center justify-between px-4 py-3 text-left bg-slate-800 hover:bg-slate-700 border-b border-slate-800 transition"
                  >
                    <span className="font-semibold text-white">
                      {section}
                    </span>

                    <span className="text-sky-400 text-lg font-bold">
                      {isOpen ? "−" : "+"}
                    </span>
                  </button>

                  {isOpen && (
                    <div className="p-4 border-t border-slate-800 space-y-4">
                      {sectionFields.map((field) => {
                        const fieldType =
                          normalizeFieldType(field);

                        return (
                          <div key={field.label}>
                            {fieldType === "tag" ? (
                              <>
                                <Checkbox
                                  label={field.label}
                                  checked={Boolean(
                                    values[field.label]
                                  )}
                                  onChange={(checked) =>
                                    updateValue(
                                      field.label,
                                      checked
                                    )
                                  }
                                />

                                {field.notes && (
                                  <p className="text-xs text-slate-500 mt-1 ml-7">
                                    {field.notes}
                                  </p>
                                )}
                              </>
                            ) : fieldType ===
                              "textarea" ? (
                              <>
                                <FormLabel>
                                  {field.label}
                                </FormLabel>

                                <TextArea
                                  rows={2}
                                  value={String(
                                    values[field.label] ??
                                      ""
                                  )}
                                  onChange={(value) =>
                                    updateValue(
                                      field.label,
                                      value
                                    )
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
                                <FormLabel>
                                  {field.label}
                                </FormLabel>

                                <Input
                                  value={String(
                                    values[field.label] ??
                                      ""
                                  )}
                                  onChange={(value) =>
                                    updateValue(
                                      field.label,
                                      value
                                    )
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
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            }
          )
        )}
      </div>

      <div className="mt-6">
        <Button
          fullWidth
          variant="secondary"
          onClick={handleSaveNext}
        >
          Save & Next Document
        </Button>
      </div>

      {message && (
        <p className="text-sm text-slate-400 mt-4">
          {message}
        </p>
      )}
    </aside>
  );
}