/**
 * Global Color System - 5 Star Hotel Management
 * Consistent color meanings across all modules
 */

export const COLORS = {
  // Status Colors
  STATUS: {
    AVAILABLE: {
      bg: 'bg-green-100',
      border: 'border-green-300',
      text: 'text-green-700',
      badge: 'bg-green-500',
      meaning: 'Available, Positive, Success, Ready'
    },
    RISK: {
      bg: 'bg-red-100',
      border: 'border-red-300',
      text: 'text-red-700',
      badge: 'bg-red-500',
      meaning: 'Risk, Overdue, Critical, Dirty, Urgent'
    },
    ATTENTION: {
      bg: 'bg-orange-100',
      border: 'border-orange-300',
      text: 'text-orange-700',
      badge: 'bg-orange-500',
      meaning: 'Attention, Warning, Priority, High Priority'
    },
    INFO: {
      bg: 'bg-blue-100',
      border: 'border-blue-300',
      text: 'text-blue-700',
      badge: 'bg-blue-500',
      meaning: 'Informational, Normal, Neutral'
    },
    OCCUPIED: {
      bg: 'bg-purple-100',
      border: 'border-purple-300',
      text: 'text-purple-700',
      badge: 'bg-purple-500',
      meaning: 'Occupied, In-Use, VIP'
    },
    PENDING: {
      bg: 'bg-yellow-100',
      border: 'border-yellow-300',
      text: 'text-yellow-700',
      badge: 'bg-yellow-500',
      meaning: 'Pending, In-Progress, Cleaning'
    }
  },

  // Room Status Mapping
  ROOM_STATUS: {
    available: 'AVAILABLE',
    dirty: 'RISK',
    cleaning: 'PENDING',
    inspected: 'AVAILABLE',
    occupied: 'OCCUPIED',
    out_of_order: 'RISK',
    out_of_service: 'ATTENTION'
  },

  // Housekeeping Status Mapping
  HK_STATUS: {
    clean: 'AVAILABLE',
    dirty: 'RISK',
    inspected: 'AVAILABLE',
    cleaning: 'PENDING'
  },

  // Financial Status Mapping
  FINANCIAL: {
    paid: 'AVAILABLE',
    pending: 'PENDING',
    overdue: 'RISK',
    partial: 'ATTENTION'
  },

  // Priority Levels
  PRIORITY: {
    urgent: 'RISK',
    high: 'ATTENTION',
    medium: 'INFO',
    low: 'AVAILABLE'
  }
};

/**
 * Get color classes for a status
 * @param {string} category - Category (e.g., 'ROOM_STATUS', 'HK_STATUS')
 * @param {string} status - Status value
 * @returns {object} Color classes (bg, border, text, badge)
 */
export const getStatusColor = (category, status) => {
  const statusKey = COLORS[category]?.[status];
  return COLORS.STATUS[statusKey] || COLORS.STATUS.INFO;
};
