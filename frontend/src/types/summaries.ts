export type SummaryDocument = {
  id: string;
  filename: string;

  originalSummary: string;

  nativeText: string;

  extractedText: string;

  linkedEntries: {
    label: string;
    value: string;
  }[];

  outlineItems: {
    id: string;
    title: string;
    linkedText: string;
  }[];
};






