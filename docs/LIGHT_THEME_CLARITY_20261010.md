# Light theme clarity and welcome typography

## Scope

- Keep existing thin border widths. Increase light-mode neutral divider contrast
  and use a stronger input outline token for fields, selects and outline buttons.
- Separate white cards from a soft grey canvas.
- Strengthen shared secondary text and migrate dashboard/command-center faded
  labels to that token. Avoid global grey-text overrides: several operational
  screens deliberately use dark surfaces even while the overall theme is light.
- Preserve dark palette values, semantic status colors and business behavior.
- Keep the translated greeting start-aligned, with regular-weight greeting text,
  a semibold dynamic user name, inherited font family and responsive sizing.
  Do not hard-code a person's name or add another font download.

## Checks

Local synthetic-data preview: light header, welcome, action card and reservation
form; dark-mode welcome; 390px narrow viewport with no welcome overflow.
Rendered form outlines measured 1px and rgb(113, 129, 152).
Contrast contracts require secondary text >=4.5:1 on common surfaces and
input outlines >=3:1 on white cards and the canvas. Decorative dividers remain
lighter than form controls. Existing dark contrast contracts remain in place.
Greeting tests cover localization, missing user data, and long/non-Latin names.

No hotel records or device settings changed. The hotel's physical ASUS display
was not available for verification. After deployment, check the dashboard and
reservation form on that display at its normal brightness and Windows scaling.
