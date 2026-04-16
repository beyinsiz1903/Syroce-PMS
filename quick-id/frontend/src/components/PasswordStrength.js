import { CheckCircle2, XCircle, Shield, ShieldAlert, ShieldCheck } from 'lucide-react';

const PASSWORD_RULES = [
  { id: 'length', label: 'En az 8 karakter', test: (p) => p.length >= 8 },
  { id: 'upper', label: 'En az 1 büyük harf (A-Z)', test: (p) => /[A-Z]/.test(p) },
  { id: 'lower', label: 'En az 1 küçük harf (a-z)', test: (p) => /[a-z]/.test(p) },
  { id: 'digit', label: 'En az 1 rakam (0-9)', test: (p) => /[0-9]/.test(p) },
  { id: 'special', label: 'En az 1 özel karakter (!@#$%...)', test: (p) => /[!@#$%^&*()_+\-=[\]{}|;:,.<>?/~`]/.test(p) },
];

function getStrength(password) {
  if (!password) return { score: 0, label: '', color: '', width: '0%' };
  const passed = PASSWORD_RULES.filter(r => r.test(password)).length;
  const bonus = password.length >= 12 ? 1 : 0;
  const total = passed + bonus;

  if (total <= 2) return { score: total, label: 'Zayıf', color: 'bg-red-500', textColor: 'text-red-600', width: '25%' };
  if (total <= 3) return { score: total, label: 'Orta', color: 'bg-amber-500', textColor: 'text-amber-600', width: '50%' };
  if (total <= 4) return { score: total, label: 'Güçlü', color: 'bg-green-500', textColor: 'text-green-600', width: '75%' };
  return { score: total, label: 'Çok Güçlü', color: 'bg-emerald-500', textColor: 'text-emerald-600', width: '100%' };
}

export default function PasswordStrength({ password = '', showRules = true, compact = false }) {
  const strength = getStrength(password);
  const allPassed = PASSWORD_RULES.every(r => r.test(password));

  if (!password && !showRules) return null;

  if (compact) {
    return (
      <div className="space-y-1">
        {password && (
          <div className="flex items-center gap-2">
            <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${strength.color}`}
                style={{ width: strength.width }}
              />
            </div>
            <span className={`text-xs font-medium ${strength.textColor}`}>
              {strength.label}
            </span>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* Strength bar */}
      {password && (
        <div className="flex items-center gap-2">
          <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-300 ${strength.color}`}
              style={{ width: strength.width }}
            />
          </div>
          <div className="flex items-center gap-1">
            {allPassed ? (
              <ShieldCheck className="w-4 h-4 text-emerald-500" />
            ) : strength.score <= 2 ? (
              <ShieldAlert className="w-4 h-4 text-red-500" />
            ) : (
              <Shield className="w-4 h-4 text-amber-500" />
            )}
            <span className={`text-xs font-medium ${strength.textColor}`}>
              {strength.label}
            </span>
          </div>
        </div>
      )}

      {/* Rules checklist */}
      {showRules && (
        <div className="space-y-1">
          {PASSWORD_RULES.map((rule) => {
            const passed = password ? rule.test(password) : false;
            return (
              <div key={rule.id} className="flex items-center gap-1.5 text-xs">
                {password ? (
                  passed ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />
                  ) : (
                    <XCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
                  )
                ) : (
                  <div className="w-3.5 h-3.5 rounded-full border border-gray-300 flex-shrink-0" />
                )}
                <span className={passed ? 'text-green-700' : password ? 'text-red-500' : 'text-gray-500'}>
                  {rule.label}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export { getStrength, PASSWORD_RULES };
