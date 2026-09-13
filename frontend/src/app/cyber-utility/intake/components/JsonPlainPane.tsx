"use client";

import StructuredIntakePaneShell, {
  StructuredIntakeGroup,
} from "./StructuredIntakePaneShell";


type JsonPlainPaneProps = {
  recordCount?: number;
  packageCount?: number;
  groups?: StructuredIntakeGroup[];
};


export default function JsonPlainPane({
  recordCount = 0,
  packageCount = 0,
  groups = [],
}: JsonPlainPaneProps) {

  const comingSoon =
    recordCount === 0 &&
    packageCount === 0 &&
    groups.length === 0;


  return (
    <StructuredIntakePaneShell
      title="JSON — Plain"
      subtitle="Generic JSON arrays, objects, nested records, JSONL, and other structured JSON datasets."
      recordCount={recordCount}
      packageCount={packageCount}
      groupLabel="Datasets"
      groups={groups}
      comingSoon={comingSoon}
    />
  );
}