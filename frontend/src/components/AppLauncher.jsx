import React from 'react';
import { Grid3X3, Building, Globe, Zap, Network } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { useTranslation } from 'react-i18next';

export default function AppLauncher({ user }) {
  const { t } = useTranslation();

  // Yalnızca süper admin veya zincir yöneticilerine göster (isterseniz herkese açabilirsiniz)
  const isSuperAdmin = user?.role === 'super_admin' || user?.role === 'chain_admin';
  if (!isSuperAdmin) return null;

  const apps = [
    {
      id: 'pms',
      name: 'Syroce PMS',
      description: 'Otel Yönetim Sistemi (Mevcut)',
      icon: Building,
      url: '/',
      active: true,
    },
    {
      id: 'capx',
      name: 'Syroce CapX (B2B)',
      description: 'Kapalı Devre Misafir Paylaşımı',
      icon: Network,
      url: 'https://capx.replit.app/admin', // CapX URL'i (Bunu proxy ile de çözebiliriz ileride)
      active: false,
    },
    {
      id: 'agency',
      name: 'Syroce Agency',
      description: 'Acente Otomasyon Sistemi',
      icon: Globe,
      url: 'https://agency.syroce.com/admin',
      active: false,
    }
  ];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="h-9 w-9 rounded-full focus-visible:ring-0">
          <Grid3X3 className="h-[1.1rem] w-[1.1rem] text-slate-600 dark:text-slate-300" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 p-2">
        <DropdownMenuLabel className="font-normal">
          <div className="flex flex-col space-y-1">
            <p className="text-sm font-medium leading-none">Syroce Workspace</p>
            <p className="text-xs leading-none text-muted-foreground">
              Tüm platformlarınıza hızlı erişim
            </p>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <div className="grid grid-cols-2 gap-2 p-2">
          {apps.map((app) => {
            const Icon = app.icon;
            return (
              <a 
                key={app.id} 
                href={app.url} 
                target={app.id !== 'pms' ? "_blank" : "_self"} 
                rel="noreferrer"
                className={`flex flex-col items-center justify-center p-3 gap-2 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors ${app.active ? 'bg-slate-50 dark:bg-slate-800/50 border border-blue-100 dark:border-blue-900/30' : ''}`}
              >
                <div className={`p-2 rounded-full ${app.active ? 'bg-blue-100 text-blue-600 dark:bg-blue-900 dark:text-blue-300' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'}`}>
                  <Icon className="w-5 h-5" />
                </div>
                <div className="text-center">
                  <p className="text-xs font-medium text-slate-700 dark:text-slate-200">{app.name}</p>
                </div>
              </a>
            );
          })}
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem className="justify-center text-xs text-blue-600 dark:text-blue-400 font-medium cursor-pointer">
          SSO Entegrasyonları (Yakında)
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
