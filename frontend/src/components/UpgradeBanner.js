import React from 'react';
import { Zap, Crown, Lock, ArrowRight, Sparkles } from 'lucide-react';

const TIER_INFO = {
  professional: {
    label: 'Professional',
    color: 'blue',
    icon: Zap,
    gradient: 'from-blue-500 to-indigo-600',
    lightBg: 'bg-blue-50 border-blue-200',
    textColor: 'text-blue-700',
    price: '299€/ay',
  },
  enterprise: {
    label: 'Enterprise',
    color: 'purple',
    icon: Crown,
    gradient: 'from-purple-500 to-pink-600',
    lightBg: 'bg-purple-50 border-purple-200',
    textColor: 'text-purple-700',
    price: '799€/ay',
  },
};

/**
 * Inline upgrade banner shown in the nav area or content area
 * @param {string} requiredTier - 'professional' or 'enterprise'
 * @param {string} variant - 'inline' (small, in nav), 'banner' (wide, in content), 'card' (detailed)
 * @param {string} featureName - Name of the locked feature
 */
export const UpgradeBanner = ({ requiredTier = 'professional', variant = 'inline', featureName = '' }) => {
  const tier = TIER_INFO[requiredTier] || TIER_INFO.professional;
  const Icon = tier.icon;

  if (variant === 'inline') {
    return (
      <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg ${tier.lightBg} border cursor-pointer hover:shadow-sm transition-all group`}>
        <Lock className="w-3 h-3 text-gray-400 group-hover:text-gray-600 transition" />
        <span className={`text-[11px] font-medium ${tier.textColor}`}>
          {tier.label} planında
        </span>
        <ArrowRight className="w-3 h-3 text-gray-400 group-hover:translate-x-0.5 transition-transform" />
      </div>
    );
  }

  if (variant === 'nav-footer') {
    return (
      <div className={`mx-2 mt-2 mb-1 p-3 rounded-xl bg-gradient-to-r ${tier.gradient} text-white shadow-lg cursor-pointer hover:shadow-xl transition-all`}>
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4" />
          <span className="text-xs font-bold">Daha fazla özellik</span>
        </div>
        <p className="text-[10px] opacity-90 mt-1">
          {requiredTier === 'professional' 
            ? 'Channel Manager, Night Audit, Gelişmiş Raporlar...' 
            : 'AI, Revenue Management, CRM, Multi-Property...'}
        </p>
        <div className="flex items-center gap-1 mt-2 text-[10px] font-semibold opacity-90">
          <span>{tier.label} plana yükselt</span>
          <ArrowRight className="w-3 h-3" />
        </div>
      </div>
    );
  }

  if (variant === 'banner') {
    return (
      <div className={`w-full p-4 rounded-xl border-2 ${tier.lightBg} flex items-center justify-between gap-4`}>
        <div className="flex items-center gap-3">
          <div className={`p-2.5 rounded-xl bg-gradient-to-br ${tier.gradient} text-white shadow-md`}>
            <Icon className="w-5 h-5" />
          </div>
          <div>
            <h3 className={`text-sm font-bold ${tier.textColor}`}>
              {featureName ? `"${featureName}" ${tier.label} planında` : `${tier.label} Planına Yükselt`}
            </h3>
            <p className="text-xs text-gray-500 mt-0.5">
              {requiredTier === 'professional'
                ? 'Channel Manager, Folio, Night Audit, Gelişmiş Raporlar ve daha fazlası'
                : 'AI Modülleri, Revenue Management, CRM, Multi-Property ve tüm özellikler'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={`text-xs font-bold ${tier.textColor}`}>{tier.price}'dan</span>
          <div className={`px-3 py-1.5 rounded-lg bg-gradient-to-r ${tier.gradient} text-white text-xs font-bold shadow hover:shadow-md transition cursor-pointer flex items-center gap-1`}>
            Yükselt <ArrowRight className="w-3 h-3" />
          </div>
        </div>
      </div>
    );
  }

  // card variant
  return (
    <div className="max-w-md mx-auto p-6 rounded-2xl border-2 border-dashed border-gray-200 bg-white text-center">
      <div className={`inline-flex p-3 rounded-2xl bg-gradient-to-br ${tier.gradient} text-white shadow-lg mb-4`}>
        <Lock className="w-8 h-8" />
      </div>
      <h3 className="text-lg font-bold text-gray-900 mb-1">
        {featureName || 'Bu Özellik'} Kilitli
      </h3>
      <p className="text-sm text-gray-500 mb-4">
        Bu özellik <span className={`font-semibold ${tier.textColor}`}>{tier.label}</span> planında kullanılabilir.
        {requiredTier === 'professional'
          ? ' Orta ölçekli oteller için Channel Manager, Folio ve daha fazlası.'
          : ' Büyük oteller için AI, RMS, CRM ve tüm modüller.'}
      </p>
      <div className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r ${tier.gradient} text-white font-bold text-sm shadow-lg hover:shadow-xl transition cursor-pointer`}>
        <Icon className="w-4 h-4" />
        {tier.label} Plana Yükselt
        <ArrowRight className="w-4 h-4" />
      </div>
      <p className="text-xs text-gray-400 mt-3">{tier.price}'dan başlayan fiyatlarla</p>
    </div>
  );
};

/**
 * Locked nav item indicator (small lock badge on nav button)
 */
export const LockedBadge = ({ tier = 'professional' }) => {
  const info = TIER_INFO[tier] || TIER_INFO.professional;
  return (
    <span className={`ml-1 inline-flex items-center justify-center w-4 h-4 rounded-full ${info.lightBg} border`}>
      <Lock className={`w-2.5 h-2.5 ${info.textColor}`} />
    </span>
  );
};

export default UpgradeBanner;
