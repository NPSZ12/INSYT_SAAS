"use client";

import StructuredIntakePaneShell, {
  StructuredIntakeGroup,
} from "./StructuredIntakePaneShell";


type JsonGooglePaneProps = {
  recordCount?: number;
  packageCount?: number;
  groups?: StructuredIntakeGroup[];
};


export default function JsonGooglePane({
  recordCount = 0,
  packageCount = 0,
  groups = [],
}: JsonGooglePaneProps) {

  const comingSoon =
    recordCount === 0 &&
    packageCount === 0 &&
    groups.length === 0;


  return (
    <StructuredIntakePaneShell
      title="JSON — Google"
      subtitle="Google Workspace and related structured exports preserved in their native logical groupings."
      recordCount={recordCount}
      packageCount={packageCount}
      groupLabel="Collections"
      groups={groups}
      comingSoon={comingSoon}
    />
  );
}