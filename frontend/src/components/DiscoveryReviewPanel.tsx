"use client";

import { useEffect, useState } from "react";

import Button from "./Button";
import FormLabel from "./FormLabel";
import Select from "./Select";
import TextArea from "./TextArea";
import { apiPost } from "../lib/api";

type DiscoveryField = {
  section: string;
  label: string;
  type?: string;
  format?: string;
  notes?: string;
};

type DiscoveryReviewPanelProps = {
  projectId: string;
  batchId: string;
  docId: string;
  fields: DiscoveryField[];
};

export default function DiscoveryReviewPanel({
  projectId,
  batchId,
  docId,
  fields,
}: DiscoveryReviewPanelProps) {
  const [selectedTags, setSelectedTags] =
    useState<Record<string, string>>({});

  const [notesBySection, setNotesBySection] =
    useState<Record<string, string>>({});

  const [openSections, setOpenSections] =
    useState<Record<string, boolean>>({});

  const [message, setMessage] = useState("");

  const groupedFields = fields.reduce<Record<string, DiscoveryField[]>>(
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

  useEffect(() => {
    const initialSelections: Record<string, string> = {};
    const initialOpenState: Record<string, boolean> = {};

    Object.keys(groupedFields).forEach((section) => {
      initialSelections[section] = "";
      initialOpenState[section] = false;
    });

    setSelectedTags(initialSelections);
    setOpenSections(initialOpenState);
  }, [fields]);

  function updateSelectedTag(section: string, value: string) {
    setSelectedTags((current) => ({
      ...current,
      [section]: value,
    }));
  }

  function updateNotes(section: string, value: string) {
    setNotesBySection((current) => ({
      ...current,
      [section]: value,
    }));
  }

  function toggleSection(section: string) {
    setOpenSections((current) => ({
      ...current,
      [section]: !current[section],
    }));
  }

  function handleSaveNext() {
    apiPost("/api/review/save-next", {
      project_id: projectId,
      batch_id: batchId,
      doc_id: docId,
      discovery_tags: selectedTags,
      discovery_notes: notesBySection,
    })
      .then(() => {
        setMessage("Discovery coding saved. Ready for next document.");
      })
      .catch((error: any) => {
        console.error(error);
        setMessage("Discovery coding save failed.");
      });
  }

  return (
    <aside className="bg-slate-900 border border-slate-800 rounded-2xl h-full flex flex-col overflow-hidden">
      <div className="shrink-0 p-6 border-b border-slate-800">
        <h2 className="text-lg font-semibold text-white">
          Discovery Coding Panel
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {Object.entries(groupedFields).length === 0 ? (
          <p className="text-sm text-slate-500">
            No Discovery template fields loaded.
          </p>
        ) : (
          <div className="space-y-3">
            {Object.entries(groupedFields).map(([section, sectionFields]) => {
              const isOpen = openSections[section] ?? false;

              return (
                <div
                  key={section}
                  className="bg-slate-950 border border-slate-800 rounded-xl overflow-hidden"
                >
                  <button
                    type="button"
                    onClick={() => toggleSection(section)}
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
                      <div>
                        <FormLabel>{section}</FormLabel>

                        <Select
                          value={selectedTags[section] || ""}
                          onChange={(value) =>
                            updateSelectedTag(section, value)
                          }
                        >
                          <option value="">Select one...</option>

                          {sectionFields.map((field) => (
                            <option
                              key={`${section}-${field.label}`}
                              value={field.label}
                            >
                              {field.label}
                            </option>
                          ))}
                        </Select>
                      </div>

                      <div>
                        <FormLabel>Notes</FormLabel>

                        <TextArea
                          rows={2}
                          value={notesBySection[section] || ""}
                          onChange={(value) =>
                            updateNotes(section, value)
                          }
                        />
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="shrink-0 border-t border-slate-800 p-6 space-y-3">
        <Button fullWidth variant="secondary" onClick={handleSaveNext}>
          Save & Next Document
        </Button>

        {message && (
          <p className="text-sm text-slate-400 mt-2">
            {message}
          </p>
        )}
      </div>
    </aside>
  );
}