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

  recordCount = 0,
  packageCount = 0,

  groupLabel = "Groups",

  groups = [],

  comingSoon = false,
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

              {comingSoon ? (
                <span className="cyber2-source-pane__status">
                  Coming Soon
                </span>
              ) : null}

            </div>

            <div className="cyber2-source-pane__subtitle">
              {subtitle}
            </div>

          </div>


          <div className="cyber2-source-pane__summary">

            <div className="cyber2-source-pane__counts">

              <span>
                Records:{" "}
                <strong>
                  {formatCount(recordCount)}
                </strong>
              </span>

              <span className="cyber2-source-pane__separator">
                •
              </span>

              <span>
                Packages:{" "}
                <strong>
                  {formatCount(packageCount)}
                </strong>
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

          {comingSoon ? (

            <div className="cyber2-source-pane__coming-soon">

              <div className="cyber2-source-pane__coming-soon-title">
                Coming Soon
              </div>

              <div className="cyber2-source-pane__coming-soon-text">
                This structured-data source adapter has been reserved
                in Cyber² Intake and will use the same INSYT fast-lane
                detection, document assignment, Files promotion, and
                downstream Cyber² workflow.
              </div>

            </div>

          ) : null}


          {!comingSoon &&
          groups.length > 0 ? (

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


          {!comingSoon &&
          groups.length === 0 &&
          !children ? (

            <div className="cyber2-source-pane__empty">
              No structured records are currently available.
            </div>

          ) : null}


          {children}

        </div>

      ) : null}

    </section>
  );
}