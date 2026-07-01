import {
  ReservationCalendar, ReservationLineage, GroupBookingsPage, DepositTrackingPage,
  GroupFolioPage, NoShowAnalytics, GroupReservations, ArrivalList, DepartureList,
  NoShowToday,
} from "./lazyPages";

export function reservationRoutes({ p }) {
  return [
    { path: "/reservation-calendar", ...p(ReservationCalendar) },
    { path: "/app/reservation-calendar", ...p(ReservationCalendar) },
    { path: "/reservation-lineage", ...p(ReservationLineage), wrapLayout: true, layoutModule: "channel-manager" },
    { path: "/group-bookings-manage", ...p(GroupBookingsPage), wrapLayout: true, layoutModule: "group-bookings" },
    { path: "/deposit-tracking", ...p(DepositTrackingPage), wrapLayout: true, layoutModule: "deposits" },
    { path: "/group-folio", ...p(GroupFolioPage), wrapLayout: true, layoutModule: "group_folio" },
    { path: "/no-show-analytics", ...p(NoShowAnalytics) },
    { path: "/group-reservations", ...p(GroupReservations) },
    { path: "/arrival-list", ...p(ArrivalList), wrapLayout: true, layoutModule: "pms" },
    { path: "/departure-list", ...p(DepartureList), wrapLayout: true, layoutModule: "departure_list" },
    { path: "/no-show-today", ...p(NoShowToday), wrapLayout: true, layoutModule: "no_show_today" },
  ];
}
