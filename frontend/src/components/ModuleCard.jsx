import React, { memo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

const ModuleCard = memo(({ module }) => {
  const navigate = useNavigate();
  const Icon = module.icon;

  return (
    <Card
      onClick={() => navigate(module.path)}
      className="cursor-pointer hover:shadow-lg transition-all duration-200 transform hover:-translate-y-1"
      style={{ borderTop: `4px solid ${module.color}` }}
    >
      <CardHeader className="p-4">
        <div className="flex items-start justify-between">
          <div style={{
            padding: '0.75rem',
            borderRadius: '0.75rem',
            background: `${module.color}15`,
            marginBottom: '0.5rem'
          }}>
            <Icon style={{ color: module.color }} className="w-6 h-6 md:w-8 md:h-8" />
          </div>
          {module.badge && (
            <span className="px-2 py-1 text-xs font-semibold text-white bg-gradient-to-r from-purple-500 to-pink-500 rounded-full">
              {module.badge}
            </span>
          )}
        </div>
        <CardTitle className="text-base md:text-lg" style={{ fontFamily: 'Space Grotesk' }}>
          {module.title}
        </CardTitle>
        <CardDescription className="text-xs md:text-sm">{module.description}</CardDescription>
      </CardHeader>
      {module.stats && (
        <CardContent className="p-4 pt-0">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <div className="text-gray-500">Rooms</div>
              <div className="text-lg font-bold">{module.stats.total_rooms || 0}</div>
            </div>
            <div>
              <div className="text-gray-500">Occupancy</div>
              <div className="text-lg font-bold">{(module.stats.occupancy_rate || 0).toFixed(1)}%</div>
            </div>
          </div>
        </CardContent>
      )}
    </Card>
  );
}, (prevProps, nextProps) => {
  // Custom comparison - only re-render if module data actually changed
  return JSON.stringify(prevProps.module) === JSON.stringify(nextProps.module);
});

ModuleCard.displayName = 'ModuleCard';

export default ModuleCard;
