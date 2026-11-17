"use client";

import StructuredIntakePaneShell, {
  StructuredIntakeGroup,
} from "./StructuredIntakePaneShell";


type JsonSalesforcePaneProps = {
  fileCount?: number;
  recordCount?: number;
  packageCount?: number;
  objects?: StructuredIntakeGroup[];
};


export default function JsonSalesforcePane({
  fileCount = 0,
  recordCount = 0,
  packageCount = 0,
  objects = [],
}: JsonSalesforcePaneProps) {

  const comingSoon =
    recordCount === 0 &&
    packageCount === 0 &&
    objects.length === 0;


  return (
    <StructuredIntakePaneShell
      title="JSON — Salesforce"
      subtitle="Salesforce structured records preserved by object type, source record ID, and related-record relationships."
      fileCount={fileCount}
      recordCount={recordCount}
      packageCount={packageCount}
      groupLabel="Salesforce Objects"
      groups={objects}
      comingSoon={comingSoon}
    />
  );
}