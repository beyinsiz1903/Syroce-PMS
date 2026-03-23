import React, { useState } from 'react';
import { Plus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

/**
 * Floating Action Button (FAB) - Quick Actions Menu
 * Positioned at bottom-right, expands on click
 */
const FloatingActionButton = ({ actions = [] }) => {
  const [isOpen, setIsOpen] = useState(false);

  if (!actions || actions.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50">
      {/* Action Items (shown when open) */}
      {isOpen && (
        <div className="absolute bottom-20 right-0 space-y-3 mb-2 flex flex-col items-end">
          {actions.map((action, idx) => (
            <div
              key={idx}
              className="flex items-center justify-end gap-2 animate-in slide-in-from-bottom duration-200"
              style={{ animationDelay: `${idx * 50}ms` }}
            >
              {/* Action Label */}
              <div className="bg-gray-900 text-white text-xs px-3 py-1.5 rounded-full shadow-lg whitespace-nowrap">
                {action.label}
              </div>

              {/* Action Button */}
              <Button
                size="icon"
                onClick={() => {
                  action.onClick();
                  setIsOpen(false);
                }}
                className={`w-11 h-11 rounded-full shadow-lg ${action.color || 'bg-blue-600 hover:bg-blue-700'}`}
                title={action.label}
              >
                {action.icon}
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* Main FAB Button */}
      <Button
        onClick={() => setIsOpen(!isOpen)}
        className={`w-16 h-16 rounded-full shadow-2xl transition-all duration-300 ${
          isOpen 
            ? 'bg-red-600 hover:bg-red-700 rotate-45' 
            : 'bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 scale-100 hover:scale-110'
        }`}
        title="Quick Actions"
      >
        {isOpen ? (
          <X className="w-8 h-8" />
        ) : (
          <Plus className="w-8 h-8" />
        )}
      </Button>

      {/* Backdrop (when open) */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/20 -z-10"
          onClick={() => setIsOpen(false)}
        />
      )}
    </div>
  );
};

export default FloatingActionButton;
