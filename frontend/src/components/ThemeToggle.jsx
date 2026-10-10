import React from 'react';
import { useTranslation } from 'react-i18next';
import { useTheme } from 'next-themes';
import { useBorderPreference } from '@/hooks/useBorderPreference';
import { Sun, Moon, Monitor, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuCheckboxItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

// Acik / Koyu / Sistem secici (header). next-themes documentElement'e .dark
// sinifini ekler; tum tema renkleri index.css'teki CSS degiskenlerinden (HSL)
// gelir. Tercih localStorage'da (storageKey="syroce-theme") kalici tutulur.
const ThemeToggle = () => {
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();
  const [prominentBorders, setProminentBorders] = useBorderPreference();

  const options = [
    { value: 'light', label: t('settings.themeLight', 'Açık'), icon: Sun },
    { value: 'dark', label: t('settings.themeDark', 'Koyu'), icon: Moon },
    { value: 'system', label: t('settings.themeSystem', 'Sistem'), icon: Monitor },
  ];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="h-8 w-8 p-0 dark:text-gray-100"
          data-testid="theme-toggle"
          aria-label={t('settings.theme', 'Tema')}
        >
          <Sun className="w-4 h-4 hidden dark:block" />
          <Moon className="w-4 h-4 block dark:hidden" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {options.map((o) => {
          const Icon = o.icon;
          return (
            <DropdownMenuItem
              key={o.value}
              onClick={() => setTheme(o.value)}
              data-testid={`theme-option-${o.value}`}
              className="gap-2 cursor-pointer"
            >
              <Icon className="w-4 h-4" />
              <span>{o.label}</span>
              {theme === o.value ? <Check className="w-4 h-4 ml-auto" /> : null}
            </DropdownMenuItem>
          );
        })}
        <DropdownMenuSeparator />
        <DropdownMenuCheckboxItem checked={prominentBorders} onCheckedChange={setProminentBorders}
          data-testid="prominent-borders-toggle">
          {t('settings.prominentBorders', 'Prominent borders')}
        </DropdownMenuCheckboxItem>
        <p className="max-w-56 px-2 pb-2 text-xs text-muted-foreground">
          {t('settings.prominentBordersHelp', 'Stronger light-mode outlines. Saved only in this browser.')}
        </p>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default ThemeToggle;
