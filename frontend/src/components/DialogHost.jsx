import { useEffect, useState } from 'react';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { AlertTriangle, Info, HelpCircle } from 'lucide-react';
import { _registerDialogHost, _resolveDialog } from '@/lib/dialogs';

/**
 * Uygulama içi şık modal — native window.confirm/alert/prompt yerine.
 * App köküne tek defa mount edilir. dialogs.js modülünden imperatif olarak çağrılır.
 */
export default function DialogHost() {
  const [state, setState] = useState({ open: false });
  const [promptValue, setPromptValue] = useState('');

  useEffect(() => {
    _registerDialogHost(setState);
    return () => _registerDialogHost(null);
  }, []);

  useEffect(() => {
    if (state.open && state.type === 'prompt') {
      setPromptValue(state.defaultValue || '');
    }
  }, [state.open, state.type, state.defaultValue]);

  const close = (val) => {
    setState({ open: false });
    _resolveDialog(val);
  };

  const handleCancel = () => {
    if (state.type === 'confirm') close(false);
    else if (state.type === 'prompt') close(null);
    else close(undefined);
  };

  const handleConfirm = () => {
    if (state.type === 'prompt') close(promptValue);
    else if (state.type === 'confirm') close(true);
    else close(undefined);
  };

  if (!state.open) return null;

  const isDanger = state.variant === 'danger';
  const Icon = state.type === 'alert' ? Info : isDanger ? AlertTriangle : HelpCircle;
  const iconColor = isDanger ? 'text-red-600' : state.type === 'alert' ? 'text-blue-600' : 'text-amber-600';
  const confirmText = state.confirmText || (state.type === 'alert' ? 'Tamam' : 'Onayla');
  const cancelText = state.cancelText || 'İptal';
  const title = state.title || (state.type === 'alert' ? 'Bilgi' : isDanger ? 'Onaylıyor musunuz?' : 'Onay');

  return (
    <AlertDialog open={state.open} onOpenChange={(o) => { if (!o) handleCancel(); }}>
      <AlertDialogContent
        className="max-w-md rounded-xl border-gray-200 shadow-2xl"
        data-testid="app-dialog"
      >
        <form
          onSubmit={(e) => { e.preventDefault(); handleConfirm(); }}
        >
        <AlertDialogHeader>
          <div className="flex items-start gap-3">
            <div className={`flex-shrink-0 mt-0.5 ${iconColor}`}>
              <Icon className="w-6 h-6" />
            </div>
            <div className="flex-1 min-w-0">
              <AlertDialogTitle className="text-base font-semibold text-gray-900">
                {title}
              </AlertDialogTitle>
              {state.message && (
                <AlertDialogDescription className="mt-1.5 text-sm text-gray-600 whitespace-pre-line break-words">
                  {state.message}
                </AlertDialogDescription>
              )}
            </div>
          </div>
        </AlertDialogHeader>

        {state.type === 'prompt' && (
          <div className="px-9">
            <Input
              autoFocus
              value={promptValue}
              onChange={(e) => setPromptValue(e.target.value)}
              placeholder={state.placeholder || ''}
              data-testid="dialog-prompt-input"
            />
          </div>
        )}

        <AlertDialogFooter className="gap-2">
          {state.type !== 'alert' && (
            <Button
              type="button"
              variant="outline"
              onClick={handleCancel}
              data-testid="dialog-cancel-btn"
            >
              {cancelText}
            </Button>
          )}
          <Button
            type="submit"
            autoFocus={state.type !== 'prompt'}
            className={isDanger ? 'bg-red-600 hover:bg-red-700 text-white' : ''}
            data-testid="dialog-confirm-btn"
          >
            {confirmText}
          </Button>
        </AlertDialogFooter>
        </form>
      </AlertDialogContent>
    </AlertDialog>
  );
}
