import { SummaryDocument } from "../types/summaries";

export const summariesDocuments: SummaryDocument[] = [
  {
    id: "AL_00000001",

    filename: "AL_00000001.pdf",

    originalSummary:
      "Patient reports cervical pain radiating into left shoulder. MRI demonstrates C5-C6 disc protrusion.",

    nativeText:
      "Native PDF viewer content placeholder.",

    extractedText:
      "OCR Extracted Text:\n\nPatient reports cervical pain radiating into left shoulder.\nMRI findings demonstrate C5-C6 disc protrusion.",

    linkedEntries: [
      {
        label: "Provider",
        value: "Ballad Health",
      },
      {
        label: "Diagnosis",
        value: "Cervical Pain",
      },
      {
        label: "MRI",
        value: "C5-C6 Disc Protrusion",
      },
    ],

    outlineItems: [
      {
        id: "1",
        title: "Cervical Pain",
        linkedText:
          "Patient reports cervical pain radiating into left shoulder.",
      },
      {
        id: "2",
        title: "MRI Findings",
        linkedText:
          "MRI findings demonstrate C5-C6 disc protrusion.",
      },
    ],
  },

  {
    id: "AL_00000002",

    filename: "AL_00000002.pdf",

    originalSummary:
      "Patient treated for lumbar strain following accident.",

    nativeText:
      "Native PDF content for lumbar strain document.",

    extractedText:
      "OCR Extracted Text:\n\nPatient treated for lumbar strain following accident.",

    linkedEntries: [
      {
        label: "Diagnosis",
        value: "Lumbar Strain",
      },
    ],

    outlineItems: [
      {
        id: "1",
        title: "Lumbar Injury",
        linkedText:
          "Patient treated for lumbar strain following accident.",
      },
    ],
  },
];






