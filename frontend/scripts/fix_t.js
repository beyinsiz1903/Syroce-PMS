const fs = require('fs');
const files = [
  'pages/DataModelDashboard.jsx',
  'pages/GoLiveDashboardPage.jsx',
  'pages/IncidentDashboardPage.jsx',
  'pages/LandingPage.jsx',
  'pages/POSExtensions.jsx',
  'pages/ProductionRolloutPage.jsx'
];

for (const file of files) {
  const p = `/Users/syroce/Documents/GitHub/SyrocePMS/frontend/src/${file}`;
  let code = fs.readFileSync(p, 'utf8');
  
  if (code.includes('const { t } = useTranslation();')) {
      console.log(`Already has t in ${file}`);
      continue;
  }

  // Regex to inject after function ComponentName() { or const ComponentName = () => {
  // Let's manually find the component name from the filename
  const compName = file.split('/')[1].replace('.jsx', '');
  
  // Also try default export function
  let replaced = false;
  
  const fnMatch = code.match(new RegExp(`function\\s+${compName}\\s*\\([^)]*\\)\\s*{`));
  if (fnMatch) {
      code = code.replace(fnMatch[0], `${fnMatch[0]}\n  const { t } = useTranslation();\n`);
      replaced = true;
  }
  
  if (!replaced) {
      const arrowMatch = code.match(new RegExp(`const\\s+${compName}\\s*=\\s*(?:\\([^)]*\\)|props)\\s*=>\\s*{`));
      if (arrowMatch) {
          code = code.replace(arrowMatch[0], `${arrowMatch[0]}\n  const { t } = useTranslation();\n`);
          replaced = true;
      }
  }

  if (!replaced) {
      const defMatch = code.match(/export default function\s*\([^)]*\)\s*{/);
      if (defMatch) {
          code = code.replace(defMatch[0], `${defMatch[0]}\n  const { t } = useTranslation();\n`);
          replaced = true;
      }
  }
  
  if (replaced) {
      fs.writeFileSync(p, code, 'utf8');
      console.log(`Fixed ${file}`);
  } else {
      console.log(`Failed to find injection point in ${file}`);
  }
}
