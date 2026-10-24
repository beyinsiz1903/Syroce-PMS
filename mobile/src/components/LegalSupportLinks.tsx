import React, { useState } from 'react';
import { Linking } from 'react-native';
import { Body, Button, Card } from './ui';
import { tr } from '../i18n/tr';
import { spacing, useTheme } from '../theme';
import { PUBLIC_LINKS } from '../utils/publicLinks';

export function LegalSupportLinks() {
  const c = useTheme();
  const [failed, setFailed] = useState(false);
  const open = async (url: string) => {
    setFailed(false);
    try { await Linking.openURL(url); }
    catch { setFailed(true); }
  };

  return (
    <Card testID="legal-support-links" style={{ gap: spacing.sm }}>
      <Button title={tr.app.privacyPolicy} icon="shield-checkmark-outline" variant="ghost" testID="privacy-policy-link" onPress={() => { void open(PUBLIC_LINKS.privacy); }} fullWidth />
      <Button title={tr.app.support} icon="help-circle-outline" variant="ghost" testID="support-link" onPress={() => { void open(PUBLIC_LINKS.support); }} fullWidth />
      {failed ? <Body style={{ color: c.danger }} accessibilityLiveRegion="polite">{tr.app.externalLinkError}</Body> : null}
    </Card>
  );
}
