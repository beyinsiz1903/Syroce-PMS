import React, { useId } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Construction, Rocket, Settings, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const EmptyState = ({ 
  title,
  description,
  icon: Icon = Construction,
  actionText,
  onAction,
  actionIcon: ActionIcon = Plus,
  comingSoon = false,
  setupRequired = false
}) => {
  const { t } = useTranslation();
  const titleId = useId();
  const descriptionId = useId();
  const resolvedTitle = title || t('uiQuality.emptyState.defaultTitle', {
    defaultValue: 'Nothing to show yet',
  });
  const resolvedDescription = description || t('uiQuality.emptyState.defaultDescription', {
    defaultValue: 'Adjust your filters or create the first record to get started.',
  });

  return (
    <Card
      className="border-2 border-dashed"
      role="status"
      aria-live="polite"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
    >
      <CardContent className="p-8 text-center">
        <div className={`inline-flex items-center justify-center w-16 h-16 rounded-full mb-4 ${
          comingSoon ? 'bg-indigo-100' : 
          setupRequired ? 'bg-blue-100' : 
          'bg-gray-100'
        }`}>
          <Icon aria-hidden="true" focusable="false" className={`w-8 h-8 ${
            comingSoon ? 'text-indigo-600' : 
            setupRequired ? 'text-blue-600' : 
            'text-gray-400'
          }`} />
        </div>
        
        <h3 id={titleId} className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
          {resolvedTitle}
        </h3>
        
        <p id={descriptionId} className="text-sm text-gray-600 dark:text-gray-300 mb-4 max-w-md mx-auto">
          {resolvedDescription}
        </p>

        {comingSoon && (
          <Badge className="bg-indigo-600 text-white mb-4">
            <Rocket aria-hidden="true" className="w-3 h-3 mr-1" />
            {t('uiQuality.emptyState.comingSoon', { defaultValue: 'Coming soon' })}
          </Badge>
        )}

        {setupRequired && (
          <Badge className="bg-blue-700 text-white mb-4">
            <Settings aria-hidden="true" className="w-3 h-3 mr-1" />
            {t('uiQuality.emptyState.setupRequired', { defaultValue: 'Setup required' })}
          </Badge>
        )}

        {actionText && onAction && (
          <Button type="button" onClick={onAction} className="mt-2">
            {ActionIcon && <ActionIcon aria-hidden="true" className="w-4 h-4 mr-2" />}
            {actionText}
          </Button>
        )}
      </CardContent>
    </Card>
  );
};

export default EmptyState;
