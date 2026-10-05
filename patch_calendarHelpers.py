import re

file_path = 'frontend/src/pages/calendar/calendarHelpers.jsx'
with open(file_path, 'r') as f:
    content = f.read()

pattern = r"(if \(channel\.includes\('setur'\)\) return \{ bg: '#0D9488', border: '#0F766E', label: 'Setur' \};)"
replacement = r"""\1
  if (channel.includes('etstur') || channel === 'ets') return { bg: '#0891B2', border: '#0E7490', label: 'Etstur' };
  if (channel.includes('odamax')) return { bg: '#F59E0B', border: '#D97706', label: 'Odamax' };
  if (channel.includes('tatilsepeti')) return { bg: '#EF4444', border: '#DC2626', label: 'Tatilsepeti' };
  if (channel.includes('jolly')) return { bg: '#8B5CF6', border: '#7C3AED', label: 'Jolly' };
  if (channel.includes('hotelrunner')) return { bg: '#3B82F6', border: '#2563EB', label: 'HotelRunner' };"""

content = re.sub(pattern, replacement, content)

with open(file_path, 'w') as f:
    f.write(content)
