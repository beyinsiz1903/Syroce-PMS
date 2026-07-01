import { useNavigate } from 'react-router-dom';
import { ArrowLeftRight } from 'lucide-react';

const providers = [
  { key: 'exely', label: 'Exely', path: '/rate-manager' },
  { key: 'hotelrunner', label: 'HotelRunner', path: '/hr-rate-manager' },
];

export const ProviderToggle = ({ active }) => {
  const navigate = useNavigate();

  return (
    <div className="inline-flex items-center rounded-lg border border-zinc-200 bg-zinc-50 p-0.5" data-testid="provider-toggle">
      {providers.map((p, i) => (
        <button
          key={p.key}
          data-testid={`provider-toggle-${p.key}`}
          onClick={() => { if (p.key !== active) navigate(p.path); }}
          className={`
            relative px-4 py-1.5 text-sm font-medium rounded-md transition-all duration-200
            ${p.key === active
              ? 'bg-white text-zinc-900 shadow-sm ring-1 ring-zinc-200'
              : 'text-zinc-500 hover:text-zinc-700 hover:bg-zinc-100 cursor-pointer'}
          `}
        >
          {i === 1 && (
            <ArrowLeftRight className="inline-block w-3.5 h-3.5 mr-1.5 -mt-0.5 opacity-50" />
          )}
          {p.label}
        </button>
      ))}
    </div>
  );
};
