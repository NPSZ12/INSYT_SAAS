"use client";

import { useEffect, useState } from "react";

import AppShell from "../../../components/AppShell";

import SummariesLeftPane from "../../../components/summaries/SummariesLeftPane";
import SummariesCenterPane from "../../../components/summaries/SummariesCenterPane";
import SummariesRightPane from "../../../components/summaries/SummariesRightPane";

import { summariesDocuments } from "../../../data/summariesMockData";

type SavedSummaryQc = {
  codingStatus: string;
  qcText: string;
  updatedOutlineItems: string[];
};

function buildOutlineFromText(text: string) {
  return text
    .split(".")
    .map((item) => item.trim())
    .filter(Boolean);
}

export default function SummariesReviewPage() {
  const [selectedDocument, setSelectedDocument] =
    useState(summariesDocuments[0]);

  const [qcText, setQcText] = useState("");
  const [codingStatus, setCodingStatus] = useState("");
  const [extractedMode, setExtractedMode] = useState(true);
  const [updatedOutlineItems, setUpdatedOutlineItems] =
    useState<string[]>([]);

  const [savedQcByDocId, setSavedQcByDocId] =
    useState<Record<string, SavedSummaryQc>>({});

  function handleQcTextChange(value: string) {
    setQcText(value);
    setUpdatedOutlineItems(buildOutlineFromText(value));
  }

  function loadDocument(doc: (typeof summariesDocuments)[number]) {
    setSelectedDocument(doc);

    const saved = savedQcByDocId[doc.id];

    if (saved) {
      setQcText(saved.qcText);
      setCodingStatus(saved.codingStatus);
      setUpdatedOutlineItems(saved.updatedOutlineItems);
    } else {
      setQcText("");
      setCodingStatus("");
      setUpdatedOutlineItems([]);
    }

    setExtractedMode(true);
  }

  function handleSave() {
    if (!codingStatus) {
      alert("Please select a Document Coding status before saving.");
      return false;
    }

    if (!qcText.trim()) {
      alert("Please enter or select Summary QC text before saving.");
      return false;
    }

    setSavedQcByDocId((prev) => {
      const next = {
        ...prev,
        [selectedDocument.id]: {
          codingStatus,
          qcText,
          updatedOutlineItems,
        },
      };

      localStorage.setItem("insyt_summaries_qc", JSON.stringify(next));

      return next;
    });

    useEffect(() => {
      const stored = localStorage.getItem("insyt_summaries_qc");

      if (stored) {
        setSavedQcByDocId(JSON.parse(stored));
      }
    }, []);

    console.log("Saving Summary QC", {
      doc_id: selectedDocument.id,
      filename: selectedDocument.filename,
      coding_status: codingStatus,
      qc_text: qcText,
      updated_outline: updatedOutlineItems,
    });

    alert("Summary QC saved.");
    return true;
  }

  function handleSaveAndNext() {
    const saved = handleSave();

    if (!saved) {
      return;
    }

    const currentIndex = summariesDocuments.findIndex(
      (doc) => doc.id === selectedDocument.id
    );

    const nextDoc =
      summariesDocuments[currentIndex + 1] || summariesDocuments[0];

    const savedNext = savedQcByDocId[nextDoc.id];

    setSelectedDocument(nextDoc);

    if (savedNext) {
      setQcText(savedNext.qcText);
      setCodingStatus(savedNext.codingStatus);
      setUpdatedOutlineItems(savedNext.updatedOutlineItems);
    } else {
      setQcText("");
      setCodingStatus("");
      setUpdatedOutlineItems([]);
    }

    setExtractedMode(true);
  }

  return (
    <AppShell>
      <div className="h-screen flex bg-slate-950 text-white overflow-hidden">
        <SummariesLeftPane
          documents={summariesDocuments}
          selectedDocument={selectedDocument}
          updatedOutlineItems={updatedOutlineItems}
          savedDocIds={Object.keys(savedQcByDocId)}
          onSelectDocument={loadDocument}
          onSelectHyperlink={(text) => handleQcTextChange(text)}
        />

        <SummariesCenterPane
          document={selectedDocument}
          extractedMode={extractedMode}
          setExtractedMode={setExtractedMode}
        />

        <SummariesRightPane
          document={selectedDocument}
          qcText={qcText}
          setQcText={handleQcTextChange}
          codingStatus={codingStatus}
          setCodingStatus={setCodingStatus}
          onSave={handleSave}
          onSaveAndNext={handleSaveAndNext}
        />
      </div>
    </AppShell>
  );
}








