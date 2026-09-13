"use client";

import StructuredIntakePaneShell, {
  StructuredIntakeGroup,
} from "./StructuredIntakePaneShell";


type JsonTeamsPaneProps = {
  recordCount?: number;
  packageCount?: number;
  channels?: StructuredIntakeGroup[];
};


export default function JsonTeamsPane({
  recordCount = 0,
  packageCount = 0,
  channels = [],
}: JsonTeamsPaneProps) {

  const comingSoon =
    recordCount === 0 &&
    packageCount === 0 &&
    channels.length === 0;


  return (
    <StructuredIntakePaneShell
      title="JSON — Teams"
      subtitle="Microsoft Teams structured exports organized by team, channel, conversation, thread, and message."
      recordCount={recordCount}
      packageCount={packageCount}
      groupLabel="Teams / Channels"
      groups={channels}
      comingSoon={comingSoon}
    />
  );
}