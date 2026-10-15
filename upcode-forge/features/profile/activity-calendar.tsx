import { ProfileActivity } from "@/types/api";

const months = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

export function ActivityCalendar({ activity }: { activity: ProfileActivity }) {
  const first = new Date(`${activity.days[0].date}T00:00:00Z`);
  const leading = (first.getUTCDay() + 6) % 7;
  const cells = [
    ...Array.from({ length: leading }, () => null),
    ...activity.days,
  ];
  const weeks = Math.ceil(cells.length / 7);
  const monthLabels: { column: number; label: string }[] = [];
  let previousMonth = -1;
  for (let week = 0; week < weeks; week++) {
    const day = cells
      .slice(week * 7, week * 7 + 7)
      .find((cell) => cell !== null);
    if (day) {
      const month = new Date(`${day.date}T00:00:00Z`).getUTCMonth();
      if (month !== previousMonth) {
        monthLabels.push({ column: week + 1, label: months[month] });
        previousMonth = month;
      }
    }
  }
  const maximum = Math.max(1, ...activity.days.map((day) => day.count));
  const active = activity.days.filter((day) => day.count > 0);
  return (
    <>
      <div className="activity-scroll" aria-hidden="true">
        <div
          className="activity-chart"
          style={{ minWidth: `${weeks * 14 + 32}px` }}
        >
          <div
            className="activity-months"
            style={{ gridTemplateColumns: `repeat(${weeks}, 11px)` }}
          >
            {monthLabels.map((month) => (
              <span key={month.label} style={{ gridColumn: month.column }}>
                {month.label}
              </span>
            ))}
          </div>
          <div className="activity-body">
            <div className="activity-weekdays">
              <span>Mon</span>
              <span>Wed</span>
              <span>Fri</span>
            </div>
            <div
              className="activity-grid"
              style={{ gridTemplateColumns: `repeat(${weeks}, 11px)` }}
            >
              {cells.map((day, index) =>
                day ? (
                  <span
                    key={day.date}
                    className={`activity-cell activity-level-${day.count ? Math.max(1, Math.ceil((day.count / maximum) * 4)) : 0}`}
                    title={`${day.count} contribution${day.count === 1 ? "" : "s"} on ${day.date}`}
                  />
                ) : (
                  <span
                    className="activity-cell activity-empty"
                    key={`empty-${index}`}
                  />
                ),
              )}
            </div>
          </div>
        </div>
      </div>
      <div className="activity-footer muted small">
        <span>Public contributions · UTC</span>
        <div
          className="activity-legend"
          aria-label="Green tiles show increasing contribution counts"
        >
          Less{" "}
          {[0, 1, 2, 3, 4].map((level) => (
            <span
              key={level}
              className={`activity-cell activity-level-${level}`}
              aria-hidden="true"
            />
          ))}{" "}
          More
        </div>
      </div>
      <details className="activity-details small">
        <summary>Activity by day ({active.length} active days)</summary>
        {active.length ? (
          <ul>
            {active.map((day) => (
              <li key={day.date}>
                <time dateTime={day.date}>{day.date}</time>: {day.count}{" "}
                contribution{day.count === 1 ? "" : "s"}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">
            No public contributions in {activity.year} yet.
          </p>
        )}
      </details>
      {activity.incomplete && (
        <p className="field-error" role="status">
          Some Git activity could not be loaded. The calendar may be incomplete.
        </p>
      )}
    </>
  );
}
