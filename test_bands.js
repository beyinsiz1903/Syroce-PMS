const child_age_bands = [
  {"min_age": 0, "max_age": 6, "pricing_mode": "free", "value": 0},
  {"min_age": 7, "max_age": 11, "pricing_mode": "adult_percentage", "value": 75},
  {"min_age": 12, "max_age": 17, "pricing_mode": "adult_rate", "value": 0}
];

const bandsValid = child_age_bands.length > 0 &&
  child_age_bands[0].min_age === 0 &&
  child_age_bands[child_age_bands.length - 1].max_age === 17 &&
  child_age_bands.every((band, i, arr) => i === 0 || band.min_age === arr[i - 1].max_age + 1);

console.log("bandsValid:", bandsValid);
