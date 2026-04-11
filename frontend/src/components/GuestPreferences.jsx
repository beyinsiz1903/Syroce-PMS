import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Star, Users } from 'lucide-react';

/**
 * Guest Preferences Manager
 * Pillow type, smoking, room preferences, special requests
 */
const GuestPreferences = ({ guest }) => {
  const [prefs, setPrefs] = useState({
    pillow_type: guest?.preferences?.pillow_type || 'standard',
    smoking: guest?.preferences?.smoking || false,
    floor_preference: guest?.preferences?.floor_preference || 'high',
    foam_pillow: guest?.preferences?.foam_pillow || false,
    anti_allergen: guest?.preferences?.anti_allergen || false
  });

  const tags = guest?.tags || ['VIP', 'Corporate', 'Long-Stay'];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Star className="w-5 h-5 text-yellow-600" />
          Guest Preferences
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Tags */}
        <div>
          <label className="text-sm font-semibold mb-2 block">Tags:</label>
          <div className="flex flex-wrap gap-2">
            {tags.map((tag, idx) => (
              <Badge key={idx} variant="outline">{tag}</Badge>
            ))}
          </div>
        </div>

        {/* Pillow Type */}
        <div>
          <label className="text-sm font-semibold mb-2 block">Pillow Type:</label>
          <select
            value={prefs.pillow_type}
            onChange={(e) => setPrefs({...prefs, pillow_type: e.target.value})}
            className="w-full border rounded px-3 py-2 text-sm"
          >
            <option value="standard">Standard</option>
            <option value="firm">Firm</option>
            <option value="soft">Soft</option>
            <option value="memory_foam">Memory Foam</option>
          </select>
        </div>

        {/* Preferences Switches */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm">Smoking Room</span>
            <Switch
              checked={prefs.smoking}
              onCheckedChange={(checked) => setPrefs({...prefs, smoking: checked})}
            />
          </div>

          <div className="flex items-center justify-between">
            <span className="text-sm">Foam Pillow</span>
            <Switch
              checked={prefs.foam_pillow}
              onCheckedChange={(checked) => setPrefs({...prefs, foam_pillow: checked})}
            />
          </div>

          <div className="flex items-center justify-between">
            <span className="text-sm">Anti-allergen Set</span>
            <Switch
              checked={prefs.anti_allergen}
              onCheckedChange={(checked) => setPrefs({...prefs, anti_allergen: checked})}
            />
          </div>
        </div>

        {/* Floor Preference */}
        <div>
          <label className="text-sm font-semibold mb-2 block">Floor Preference:</label>
          <div className="flex gap-2">
            {['high', 'low', 'middle'].map(floor => (
              <button
                key={floor}
                onClick={() => setPrefs({...prefs, floor_preference: floor})}
                className={`flex-1 py-2 text-sm rounded border ${
                  prefs.floor_preference === floor
                    ? 'bg-blue-500 text-white border-blue-500'
                    : 'bg-white text-gray-700 border-gray-300'
                }`}
              >
                {floor.charAt(0).toUpperCase() + floor.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Stay History Summary */}
        <div className="mt-4 p-3 bg-purple-50 border border-purple-200 rounded">
          <div className="flex items-center gap-2 text-sm font-semibold text-purple-900">
            <Users className="w-4 h-4" />
            Stay History
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-gray-600">Total Stays:</span>
              <span className="ml-2 font-bold">12</span>
            </div>
            <div>
              <span className="text-gray-600">Total Spend:</span>
              <span className="ml-2 font-bold">$4,500</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default GuestPreferences;