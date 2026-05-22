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
  const [selectedTags, setSelectedTags] = useState<Record<string, string>>({});
  const [notesBySection, setNotesBySection] = useState<Record<string, string>>({});
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

    Object.keys(groupedFields).forEach((section) => {
      initialSelections[section] = "";
    });

    setSelectedTags(initialSelections);
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
    <aside className="bg-slate-900 border border-slate-800 rounded-2xl p-6 overflow-y-auto h-full">
      <h2 className="text-lg font-semibold mb-4 text-white">
        Discovery Coding Panel
      </h2>

      {Object.entries(groupedFields).length === 0 ? (
        <p className="text-sm text-slate-500">
          No Discovery template fields loaded.
        </p>
      ) : (
        <div className="space-y-5">
          {Object.entries(groupedFields).map(([section, sectionFields]) => (
            <div
              key={section}
              className="rounded-xl border border-slate-800 bg-slate-950 p-4"
            >
              <FormLabel>{section}</FormLabel>

              <Select
                value={selectedTags[section] || ""}
                onChange={(value) => updateSelectedTag(section, value)}
              >
                <option value="">Select one...</option>

                {sectionFields.map((field) => (
                  <option key={`${section}-${field.label}`} value={field.label}>
                    {field.label}
                  </option>
                ))}
              </Select>

              <div className="mt-3">
                <FormLabel>Notes</FormLabel>

                <TextArea
                  rows={2}
                  value={notesBySection[section] || ""}
                  onChange={(value) => updateNotes(section, value)}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-6">
        <Button fullWidth variant="secondary" onClick={handleSaveNext}>
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