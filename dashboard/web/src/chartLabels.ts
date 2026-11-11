import { TickMarkType, type Time } from "lightweight-charts";

// Time labels for Lightweight Charts, shared by the Charts page and the value charts.
//
// Times stay real UTC timestamps; only their labels are written in a time zone.
// (Shifting the timestamps themselves breaks on the night daylight saving ends:
// 1:00 to 2:00 AM happens twice, two hourly candles land on the same time, and
// the chart refuses the data.)
//
// Intraday bars are labelled in your time zone. Daily and weekly bars are
// labelled by their UTC date: Coinbase days start at 00:00 UTC and Schwab's at
// midnight Central (05:00 or 06:00 UTC), so the UTC date is right for both.
export function timeLabels(intraday: boolean) {
  const timeZone = intraday ? undefined : "UTC";
  const format = (options: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat(undefined, { ...options, timeZone });
  const year = format({ year: "numeric" });
  const month = format({ month: "short" });
  const day = format({ day: "numeric" });
  const clock = format({ hour: "numeric", minute: "2-digit" });
  const crosshair = intraday
    ? format({ weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
    : format({ weekday: "short", year: "numeric", month: "short", day: "numeric" });
  const date = (time: Time) => new Date((time as number) * 1000);

  return {
    tick(time: Time, type: TickMarkType): string {
      switch (type) {
        case TickMarkType.Year:
          return year.format(date(time));
        case TickMarkType.Month:
          return month.format(date(time));
        case TickMarkType.DayOfMonth:
          return day.format(date(time));
        default:
          return clock.format(date(time));
      }
    },
    crosshair: (time: Time) => crosshair.format(date(time)),
  };
}
