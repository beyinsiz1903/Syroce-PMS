import re

with open("frontend/src/pages/__tests__/IntegrationDestructiveGuards.test.jsx", "r") as f:
    content = f.read()

# Replace expect(screen.getByTestId('hr-callback-url')).toHaveValue(...)
# with await waitFor(() => expect(screen.getByTestId('hr-callback-url')).toHaveValue(...))
content = content.replace(
    "expect(screen.getByTestId('hr-callback-url')).toHaveValue(\n      'https://pms.syroce.com/api/channel-manager/hotelrunner/callback',\n    );",
    "await waitFor(() => expect(screen.getByTestId('hr-callback-url')).toHaveValue('https://pms.syroce.com/api/channel-manager/hotelrunner/callback'));"
)

# Also check if it's on a single line in case formatting is different
content = content.replace(
    "expect(screen.getByTestId('hr-callback-url')).toHaveValue('https://pms.syroce.com/api/channel-manager/hotelrunner/callback');",
    "await waitFor(() => expect(screen.getByTestId('hr-callback-url')).toHaveValue('https://pms.syroce.com/api/channel-manager/hotelrunner/callback'));"
)


with open("frontend/src/pages/__tests__/IntegrationDestructiveGuards.test.jsx", "w") as f:
    f.write(content)

print("patched")
