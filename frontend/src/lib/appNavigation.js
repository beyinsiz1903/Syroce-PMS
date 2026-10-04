// Application-wide bridge for code that runs outside a React component
// (Axios interceptors and authentication callbacks).  Once BrowserRouter is
// mounted, internal URLs use React Router instead of discarding in-memory UI
// state with a document navigation.
let routerNavigate = null;

export function registerAppNavigation(navigate) {
  routerNavigate = navigate;
  return () => {
    if (routerNavigate === navigate) routerNavigate = null;
  };
}

export function navigateInternal(to, options = {}) {
  if (typeof to !== "string" || !to.startsWith("/")) return false;
  if (routerNavigate) {
    routerNavigate(to, options);
    return true;
  }

  // This only runs before React has mounted (for example a fatal bootstrap
  // failure). Normal authenticated transitions always use the router bridge.
  window.location.assign(to);
  return false;
}
