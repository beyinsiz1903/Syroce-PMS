// Module-based i18n index (Task #454 — mobile design system foundation).
//
// The single large `tr` object used to live here. It is now split into
// per-area module files under `./modules` (and per-department files under
// `./modules/departments`) so each department task edits only its own
// translation file — no more merge conflicts on one giant file. This index
// is the ONLY place that re-assembles the slices back into the exact same
// `tr` shape every screen already imports, so no call site changes.
//
// Architectural rule: this index changes only in the design-system task.
// Department tasks edit their own module file (e.g. `modules/departments/spa.ts`).
import { app } from './modules/app';
import { auth } from './modules/auth';
import { tabs } from './modules/tabs';
import { hub } from './modules/hub';
import { roleSwitch } from './modules/roleSwitch';
import { today } from './modules/today';
import { checkin } from './modules/checkin';
import { checkout } from './modules/checkout';
import { walkin } from './modules/walkin';
import { guests } from './modules/guests';
import { housekeeping } from './modules/housekeeping';
import { manager } from './modules/manager';
import { more } from './modules/more';
import { errors } from './modules/errors';
import { reservations } from './modules/reservations';
import { datePicker } from './modules/datePicker';
import { availability } from './modules/availability';
import { rooms } from './modules/rooms';
import { calendar } from './modules/calendar';
import { departmentsCommon } from './modules/departments/common';
import { spa } from './modules/departments/spa';
import { mice } from './modules/departments/mice';
import { cashier } from './modules/departments/cashier';
import { accounting } from './modules/departments/accounting';
import { maintenance } from './modules/departments/maintenance';
import { procurement } from './modules/departments/procurement';
import { hr } from './modules/departments/hr';
import { revenue } from './modules/departments/revenue';
import { pos } from './modules/departments/pos';
import { guest } from './modules/guest';

export const tr = {
  app,
  auth,
  tabs,
  hub,
  roleSwitch,
  today,
  checkin,
  checkout,
  walkin,
  guests,
  housekeeping,
  manager,
  more,
  errors,
  reservations,
  datePicker,
  availability,
  rooms,
  calendar,
  departments: {
    ...departmentsCommon,
    spa,
    mice,
    cashier,
    accounting,
    maintenance,
    procurement,
    hr,
    revenue,
    pos,
  },
  guest,
};
