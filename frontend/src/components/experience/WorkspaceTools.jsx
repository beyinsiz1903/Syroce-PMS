import { lazy, Suspense, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ClipboardList, Users, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { canAccessPmsTab } from '@/utils/moduleAccess';
import { experienceScope, GUEST_CONTEXT_EVENT, readExperiencePreference, writeExperiencePreference } from '@/lib/productExperience';
const GuestContextPanel = lazy(() => import('./GuestContextPanel'));
const WorkInbox = lazy(() => import('./WorkInbox'));

export default function WorkspaceTools({ user, tenant, items }) {
  const { t } = useTranslation();
  const scope = experienceScope(user, tenant);
  const [panel, setPanel] = useState(null);
  const [guestId, setGuestId] = useState('');
  const [compact, setCompact] = useState(() => readExperiencePreference(scope, 'compact', false) === true);
  const canReadGuest = canAccessPmsTab(user, 'guests') && items.some(item => item.key === 'pms');
  const canReadWork = items.some(item => ['pms', 'tasks_workspace', 'shift_handover'].includes(item.key));
  useEffect(() => { setPanel(null); setGuestId(''); setCompact(readExperiencePreference(scope, 'compact', false) === true); }, [scope]);
  useEffect(() => {
    const open = event => { if (canReadGuest && event.detail?.guestId) { setGuestId(event.detail.guestId); setPanel('guest'); } };
    window.addEventListener(GUEST_CONTEXT_EVENT, open);
    return () => window.removeEventListener(GUEST_CONTEXT_EVENT, open);
  }, [canReadGuest]);
  useEffect(() => {
    document.documentElement.dataset.workspaceDensity = compact ? 'compact' : 'comfortable';
    return () => { delete document.documentElement.dataset.workspaceDensity; };
  }, [compact]);
  return <div className="flex items-center gap-1">
    {canReadWork && <Button variant="ghost" size="icon" aria-label={t('experience.inbox', 'İş takibi')} title={t('experience.inbox', 'İş takibi')} onClick={() => setPanel('work')}><ClipboardList className="h-4 w-4" /></Button>}
    {canReadGuest && <Button variant="ghost" size="icon" aria-label={t('experience.guestContext', 'Misafir özeti')} title={t('experience.guestContext', 'Misafir özeti')} onClick={() => { setGuestId(''); setPanel('guest'); }}><Users className="h-4 w-4" /></Button>}
    <Button variant="ghost" size="icon" className="hidden sm:inline-flex" aria-pressed={compact} aria-label={t('experience.compact', 'Kompakt görünüm')} title={t('experience.compact', 'Kompakt görünüm')} onClick={() => { writeExperiencePreference(scope, 'compact', !compact); setCompact(!compact); }}>{compact ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}</Button>
    {panel === 'guest' && canReadGuest && <Suspense fallback={<span role="status">{t('common.loading', 'Yükleniyor…')}</span>}><GuestContextPanel key={scope} scope={scope} open guestId={guestId} onOpenChange={open => !open && setPanel(null)} /></Suspense>}
    <Sheet open={panel === 'work' && canReadWork} onOpenChange={open => !open && setPanel(null)}><SheetContent className="w-full overflow-y-auto sm:max-w-2xl"><SheetHeader><SheetTitle>{t('experience.inbox', 'İş takibi')}</SheetTitle><SheetDescription>{t('experience.authorizedSources', 'Yalnızca erişiminiz olan çalışma alanları gösterilir.')}</SheetDescription></SheetHeader><div className="mt-5">{panel === 'work' && canReadWork && <Suspense fallback={<p role="status">{t('common.loading', 'Yükleniyor…')}</p>}><WorkInbox key={scope} scope={scope} items={items} onOpenSource={() => setPanel(null)} /></Suspense>}</div></SheetContent></Sheet>
  </div>;
}
