"use client";

import StructuredIntakePaneShell, {
  StructuredIntakeGroup,
} from "./StructuredIntakePaneShell";


type JsonCustomApiPaneProps = {
  recordCount?: number;
  packageCount?: number;
  groups?: StructuredIntakeGroup[];
};


export default function JsonCustomApiPane({
  recordCount = 0,
  packageCount = 0,
  groups = [],
}: JsonCustomApiPaneProps) {

  const comingSoon =
    recordCount === 0 &&
    packageCount === 0 &&
    groups.length === 0;


  return (
    <StructuredIntakePaneShell
      title="JSON — Custom/API"
      subtitle="Custom application, database, API, and otherwise unidentified structured JSON datasets."
      recordCount={recordCount}
      packageCount={packageCount}
      groupLabel="Datasets"
      groups={groups}
      comingSoon={comingSoon}
    />
  );
}