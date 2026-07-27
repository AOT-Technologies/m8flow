import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@mui/material';
import { SkeletonPlaceholder } from '@carbon/react';
import HttpService from '../services/HttpService';
import { PROCESS_STATUSES } from '../config';
import { getProcessStatus } from '../helpers';
import { ReportFilter, ReportMetadata } from '../interfaces';
import './ProcessInstanceStatusPieChart.scss';

type OwnProps = {
  variant: string;
  reportMetadata: ReportMetadata | null;
  // statuses the table is currently filtered by, so the matching slice(s) are emphasized
  selectedStatuses?: string[];
  // called when a slice/legend row is clicked so the parent can filter the table
  onStatusClick?: (status: string) => void;
};

type StatusCount = {
  status: string;
  count: number;
};

// Semantic colors aligned with the Carbon palette so the chart reads consistently
// with the rest of the app (green=done, red=error, blue=running, etc.).
const STATUS_COLORS: { [status: string]: string } = {
  complete: '#24a148',
  error: '#da1e28',
  running: '#0f62fe',
  not_started: '#8d8d8d',
  suspended: '#ff832b',
  terminated: '#a2191f',
  user_input_required: '#8a3ffc',
  waiting: '#007d79',
};

const FALLBACK_COLOR = '#6f6f6f';

// The donut is drawn as a set of concentric stroked circle arcs. pathLength=100
// normalizes each arc so a slice length is simply its percentage of the total.
const DONUT_PATH_LENGTH = 100;

export default function ProcessInstanceStatusPieChart({
  variant,
  reportMetadata,
  selectedStatuses = [],
  onStatusClick,
}: OwnProps) {
  const { t } = useTranslation();
  const isDark = useTheme().palette.mode === 'dark';
  const [statusCounts, setStatusCounts] = useState<StatusCount[] | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [activeStatus, setActiveStatus] = useState<string | null>(null);
  // guards against stale responses when filters change mid-flight
  const requestGenerationRef = useRef<number>(0);

  const apiSearchPath =
    variant === 'all' ? '/process-instances' : '/process-instances/for-me';

  // Base filters that constrain the distribution (process model, dates, initiator,
  // tenant, etc.) EXCLUDING process_status — each status gets its own count query,
  // so the donut always shows the full distribution within the other filters.
  const baseFilters: ReportFilter[] = useMemo(() => {
    if (!reportMetadata) {
      return [];
    }
    return (reportMetadata.filter_by || []).filter(
      (rf: ReportFilter) => rf.field_name !== 'process_status',
    );
  }, [reportMetadata]);

  // Only refetch when the constraining filters actually change (not on a
  // process_status-only change, which just re-highlights an existing slice).
  const baseFiltersKey = useMemo(
    () => JSON.stringify(baseFilters),
    [baseFilters],
  );

  useEffect(() => {
    if (!reportMetadata) {
      return;
    }
    requestGenerationRef.current += 1;
    const generation = requestGenerationRef.current;
    setLoading(true);

    const counts: { [status: string]: number } = {};
    let remaining = PROCESS_STATUSES.length;

    const finalizeIfDone = () => {
      remaining -= 1;
      if (remaining > 0 || generation !== requestGenerationRef.current) {
        return;
      }
      const results: StatusCount[] = PROCESS_STATUSES.map((status: string) => ({
        status,
        count: counts[status] || 0,
      }));
      setStatusCounts(results);
      setLoading(false);
    };

    PROCESS_STATUSES.forEach((status: string) => {
      const filterBy: ReportFilter[] = [
        ...baseFilters,
        { field_name: 'process_status', field_value: status, operator: 'equals' },
      ];
      HttpService.makeCallToBackend({
        path: `${apiSearchPath}?per_page=1&page=1`,
        httpMethod: 'POST',
        postBody: {
          report_metadata: { columns: [], filter_by: filterBy, order_by: [] },
        },
        successCallback: (result: any) => {
          if (generation === requestGenerationRef.current) {
            counts[status] = result?.pagination?.total || 0;
          }
          finalizeIfDone();
        },
        failureCallback: () => {
          finalizeIfDone();
        },
        onUnauthorized: () => {
          finalizeIfDone();
        },
      });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiSearchPath, baseFiltersKey]);

  const nonEmptyCounts = useMemo(
    () => (statusCounts || []).filter((sc: StatusCount) => sc.count > 0),
    [statusCounts],
  );

  const total = useMemo(
    () => nonEmptyCounts.reduce((sum, sc) => sum + sc.count, 0),
    [nonEmptyCounts],
  );

  // Precompute the arc geometry for each visible slice.
  const segments = useMemo(() => {
    let offset = 0;
    return nonEmptyCounts.map((sc: StatusCount) => {
      const length = total > 0 ? (sc.count / total) * DONUT_PATH_LENGTH : 0;
      const segment = {
        ...sc,
        length,
        offset,
        percent: total > 0 ? Math.round((sc.count / total) * 100) : 0,
      };
      offset += length;
      return segment;
    });
  }, [nonEmptyCounts, total]);

  const handleSliceClick = useCallback(
    (status: string) => {
      if (onStatusClick) {
        onStatusClick(status);
      }
    },
    [onStatusClick],
  );

  const colorForStatus = (status: string) =>
    STATUS_COLORS[status] || FALLBACK_COLOR;

  const cardTitle = t('process_instance_status_overview', {
    defaultValue: 'Process Instances by Status',
  });

  let body: React.ReactNode;
  if (loading) {
    body = (
      <div className="process-status-chart__loading">
        <SkeletonPlaceholder
          style={{ width: 180, height: 180, borderRadius: '50%' }}
        />
      </div>
    );
  } else if (total === 0) {
    body = (
      <div className="process-status-chart__empty">
        {t('no_process_instances_to_display', {
          defaultValue: 'No process instances to display.',
        })}
      </div>
    );
  } else {
    body = (
      <div className="process-status-chart__body">
        <div className="process-status-chart__donut">
          <svg
            viewBox="0 0 42 42"
            className="process-status-chart__donut-svg"
            role="img"
            aria-label={cardTitle}
          >
            {/* track ring behind the slices */}
            <circle
              cx="21"
              cy="21"
              r="15.915"
              fill="none"
              stroke={isDark ? '#393939' : '#f4f4f4'}
              strokeWidth="5"
            />
            {segments.map((seg) => {
              const isSelected = selectedStatuses.includes(seg.status);
              const isDimmed =
                activeStatus !== null && activeStatus !== seg.status;
              const isActive =
                activeStatus === seg.status || isSelected;
              return (
                <circle
                  key={seg.status}
                  cx="21"
                  cy="21"
                  r="15.915"
                  fill="none"
                  stroke={colorForStatus(seg.status)}
                  strokeWidth={isActive ? 6.5 : 5}
                  strokeOpacity={isDimmed ? 0.35 : 1}
                  strokeDasharray={`${seg.length} ${DONUT_PATH_LENGTH - seg.length}`}
                  strokeDashoffset={-seg.offset}
                  pathLength={DONUT_PATH_LENGTH}
                  transform="rotate(-90 21 21)"
                  style={{ cursor: onStatusClick ? 'pointer' : 'default' }}
                  onMouseEnter={() => setActiveStatus(seg.status)}
                  onMouseLeave={() => setActiveStatus(null)}
                  onClick={() => handleSliceClick(seg.status)}
                >
                  <title>{`${getProcessStatus(seg.status)}: ${seg.count} (${seg.percent}%)`}</title>
                </circle>
              );
            })}
          </svg>
          <div className="process-status-chart__center">
            <div className="process-status-chart__center-value">{total}</div>
            <div className="process-status-chart__center-label">
              {t('total', { defaultValue: 'Total' })}
            </div>
          </div>
        </div>
        <ul className="process-status-chart__legend">
          {segments.map((seg) => {
            const isSelected = selectedStatuses.includes(seg.status);
            return (
              <li key={seg.status}>
                <button
                  type="button"
                  className={
                    isSelected
                      ? 'process-status-chart__legend-item process-status-chart__legend-item--selected'
                      : 'process-status-chart__legend-item'
                  }
                  onClick={() => handleSliceClick(seg.status)}
                  onMouseEnter={() => setActiveStatus(seg.status)}
                  onMouseLeave={() => setActiveStatus(null)}
                >
                  <span
                    className="process-status-chart__legend-swatch"
                    style={{ backgroundColor: colorForStatus(seg.status) }}
                  />
                  <span className="process-status-chart__legend-label">
                    {getProcessStatus(seg.status)}
                  </span>
                  <span className="process-status-chart__legend-count">
                    {seg.count}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    );
  }

  return (
    <div
      className={
        isDark
          ? 'process-status-chart process-status-chart--dark'
          : 'process-status-chart'
      }
      data-testid="process-status-chart"
    >
      <h2 className="process-status-chart__title">{cardTitle}</h2>
      {body}
    </div>
  );
}
