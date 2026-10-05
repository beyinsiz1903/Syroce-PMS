import re

with open('frontend/src/pages/ReservationDetailModal.jsx', 'r') as f:
    content = f.read()

# In saveStayDates:
# We need to add `const isComplimentary = Boolean(booking?.is_complimentary);`
# And then use it for the rates.

pattern_rates = r'const rates = stayDates\(checkIn, checkOut\)\.map\(\(date\) => \{'
replacement_rates = r'''const isComplimentary = Boolean(booking?.is_complimentary);
      const rates = stayDates(checkIn, checkOut).map((date) => {'''
content = re.sub(pattern_rates, replacement_rates, content)

pattern_rate_logic = r'''rate: Number\.isFinite\(persistedRate\) && persistedRate > 0\s*\?\s*persistedRate\s*\:\s*Number\.isFinite\(configuredRate\) && configuredRate > 0\s*\?\s*configuredRate\s*\:\s*fallback,'''
replacement_rate_logic = r'''rate: isComplimentary ? 0 : (Number.isFinite(persistedRate) && persistedRate > 0
            ? persistedRate
            : Number.isFinite(configuredRate) && configuredRate > 0
              ? configuredRate
              : fallback),'''
content = re.sub(pattern_rate_logic, replacement_rate_logic, content)

pattern_some = r'if \(rates\.some\(\(rate\) => !Number\.isFinite\(rate\.rate\) \|\| rate\.rate <= 0\)\) \{'
replacement_some = r'''if (!isComplimentary && rates.some((rate) => !Number.isFinite(rate.rate) || rate.rate <= 0)) {'''
content = re.sub(pattern_some, replacement_some, content)

with open('frontend/src/pages/ReservationDetailModal.jsx', 'w') as f:
    f.write(content)
