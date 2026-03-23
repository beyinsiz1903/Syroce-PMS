import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Construction, Rocket, Settings, ExternalLink } from 'lucide-react';

const EmptyState = ({ 
  title = "Henüz Veri Yok",
  description = "Bu özellik için henüz veri bulunmuyor.",
  icon: Icon = Construction,
  actionText,
  onAction,
  comingSoon = false,
  setupRequired = false
}) => {
  return (
    <Card className="border-2 border-dashed">
      <CardContent className="p-8 text-center">
        <div className={`inline-flex items-center justify-center w-16 h-16 rounded-full mb-4 ${
          comingSoon ? 'bg-purple-100' : 
          setupRequired ? 'bg-blue-100' : 
          'bg-gray-100'
        }`}>
          <Icon className={`w-8 h-8 ${
            comingSoon ? 'text-purple-600' : 
            setupRequired ? 'text-blue-600' : 
            'text-gray-400'
          }`} />
        </div>
        
        <h3 className="text-lg font-semibold text-gray-800 mb-2">
          {title}
        </h3>
        
        <p className="text-sm text-gray-600 mb-4 max-w-md mx-auto">
          {description}
        </p>

        {comingSoon && (
          <Badge className="bg-purple-500 text-white mb-4">
            <Rocket className="w-3 h-3 mr-1" />
            Yakında Gelecek
          </Badge>
        )}

        {setupRequired && (
          <Badge className="bg-blue-500 text-white mb-4">
            <Settings className="w-3 h-3 mr-1" />
            Kurulum Gerekli
          </Badge>
        )}

        {actionText && onAction && (
          <Button onClick={onAction} className="mt-2">
            {actionText}
            <ExternalLink className="w-4 h-4 ml-2" />
          </Button>
        )}
      </CardContent>
    </Card>
  );
};

export default EmptyState;
