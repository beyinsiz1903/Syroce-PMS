// English pilot copy for the shared navigation and authentication shell.
// Untranslated operational terms intentionally fall back to Turkish rather
// than showing missing-key tokens during a live hotel shift.
export const en = {
  app: { offline: 'Connection unavailable, try again', lastUpdate: 'Last update', loading: 'Loading...', retry: 'Try again', cancel: 'Cancel', save: 'Save', confirm: 'Confirm', close: 'Close', success: 'Success', error: 'Error', empty: 'No records found', send: 'Send', nightScreen: { title: 'Night screen', hint: 'Tap the screen to exit' } },
  auth: { title: 'Sign in', email: 'Email', password: 'Password', submit: 'Sign in', logout: 'Sign out', invalid: 'Email or password is incorrect', networkError: 'Server unavailable, try again' },
  tabs: { today: 'Today', guests: 'Guests', rooms: 'Rooms', damage: 'Damage', more: 'More', settings: 'Settings', overview: 'Overview', home: 'Home', bookings: 'Bookings', bookingsShort: 'Bookings', onlineCheckin: 'Check-in', roomService: 'Room service', messages: 'Messages', loyalty: 'Loyalty', qrBadge: 'Badge', notifications: 'Notifications', myTasks: 'My tasks', tasks: 'Tasks', approvals: 'Approvals', search: 'Search', profile: 'Profile' },
  hub: { profileTitle: 'Profile', modules: 'Modules', moduleFrontdesk: 'Front desk', moduleHousekeeping: 'Housekeeping', moduleManager: 'Manager', moduleDepartments: 'Departments', moduleSpa: 'Spa', moduleMice: 'MICE', moduleCashier: 'Cashier & folio', moduleAccounting: 'Accounting', moduleMaintenance: 'Maintenance', noModules: 'No available modules' },
} as const;
