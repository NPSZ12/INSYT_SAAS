"use client";

import {
  ReactNode,
  useState,
} from "react";


export type StructuredIntakeGroup = {
  id: string;
  label: string;
  recordCount: number;
  packageCount?: number;
  secondaryLabel?: string;
};


type StructuredIntakePaneShellProps = {
  title: string;
  subtitle: string;
  fileCount?: number;

  recordCount?: number;
  packageCount?: number;

  groupLabel?: string;

  groups?: StructuredIntakeGroup[];

  comingSoon?: boolean;
  defaultExpanded?: boolean;

  children?: ReactNode;
};


function formatCount(value?: number) {
  return Number(value || 0).toLocaleString();
}


export default function StructuredIntakePaneShell({
  title,
  subtitle,

  fileCount = 0,

  groupLabel = "Groups",

  groups = [],

  defaultExpanded = false,

  children,
}: StructuredIntakePaneShellProps) {
  const [
    expanded,
    setExpanded,
  ] = useState(defaultExpanded);


  return (
    <section className="cyber2-source-pane">

      <div className="cyber2-source-pane__header">

        <button
          type="button"
          onClick={() =>
            setExpanded(
              (current) => !current
            )
          }
          className="cyber2-source-pane__toggle"
        >

          <div className="cyber2-source-pane__heading">

            <div className="cyber2-source-pane__title-row">

              <div className="cyber2-source-pane__title">
                {title}
              </div>

            </div>

            <div className="cyber2-source-pane__subtitle">
              {subtitle}
            </div>

          </div>


          <div className="cyber2-source-pane__summary">

            <div className="cyber2-source-pane__counts">
              <span>
                Total Files:{" "}
                <strong>{formatCount(fileCount)}</strong>
              </span>
            </div>


            <div className="cyber2-source-pane__expand-label">
              {expanded
                ? "Collapse ▲"
                : "Expand ▼"}
            </div>

          </div>

        </button>

      </div>


      {expanded ? (

        <div className="cyber2-source-pane__body">




          {groups.length > 0 ? (

            <div className="cyber2-source-pane__groups">

              <div className="cyber2-source-pane__groups-title">
                {groupLabel}
              </div>


              {groups.map(
                (group) => (

                  <div
                    key={group.id}
                    className="cyber2-source-pane__group"
                  >

                    <div>

                      <div className="cyber2-source-pane__group-name">
                        {group.label}
                      </div>

                      {group.secondaryLabel ? (
                        <div className="cyber2-source-pane__group-secondary">
                          {group.secondaryLabel}
                        </div>
                      ) : null}

                    </div>


                    <div className="cyber2-source-pane__group-count">

                      {formatCount(
                        group.recordCount
                      )}{" "}
                      record
                      {group.recordCount === 1
                        ? ""
                        : "s"}

                    </div>

                  </div>

                )
              )}

            </div>

          ) : null}


          {groups.length === 0 &&
          !children ? (

            <div className="cyber2-source-pane__empty">
              No files available.
            </div>

          ) : null}


          {children}

        </div>

      ) : null}

    </section>
  );
}