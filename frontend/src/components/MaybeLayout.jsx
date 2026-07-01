import React from 'react';
import Layout from './Layout';

/**
 * Hub içine "embedded" olarak yüklenen sayfalar için Layout sarımını koşullu yapar.
 * - embedded=true → Layout ATLANDI (üst hub kendi Layout'unu sağlar; çift Layout sorunu önlenir).
 * - embedded=false (varsayılan) → Layout uygulanır (sayfa standalone route'tan geldi).
 *
 * Kullanım:
 *   <MaybeLayout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout} currentModule="x">
 *     ...içerik
 *   </MaybeLayout>
 */
export default function MaybeLayout({ embedded, children, ...layoutProps }) {
  if (embedded) return <>{children}</>;
  return <Layout {...layoutProps}>{children}</Layout>;
}
