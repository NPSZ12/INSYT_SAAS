"use client";

import StructuredIntakePaneShell, {
  StructuredIntakeGroup,
} from "./StructuredIntakePaneShell";


type JsonSlackPaneProps = {
  recordCount?: number;
  packageCount?: number;
  channels?: StructuredIntakeGroup[];
};


export default function JsonSlackPane({
  recordCount = 0,
  packageCount = 0,
  channels = [],
}: JsonSlackPaneProps) {

  const comingSoon =
    recordCount === 0 &&
    packageCount === 0 &&
    channels.length === 0;


  return (
    <StructuredIntakePaneShell
      title="JSON — Slack"
      subtitle="Slack exports preserved by workspace, channel, thread, message, user, and source relationship."
      recordCount={recordCount}
      packageCount={packageCount}
      groupLabel="Channels"
      groups={channels}
      comingSoon={comingSoon}
    />
  );
}