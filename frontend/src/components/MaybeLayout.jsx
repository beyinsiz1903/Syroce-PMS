import React from 'react';
import Layout from '@/components/Layout';

export default function MaybeLayout({ embedded = false, children, ...layoutProps }) {
  if (embedded) return <>{children}</>;
  return <Layout {...layoutProps}>{children}</Layout>;
}
