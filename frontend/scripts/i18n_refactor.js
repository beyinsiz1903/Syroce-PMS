const fs = require('fs');
const path = require('path');
const babel = require('@babel/core');
const parser = require('@babel/parser');
const traverse = require('@babel/traverse').default;
const generate = require('@babel/generator').default;
const t = require('@babel/types');

const files = [
  'pages/Academy.jsx',
  'pages/AcademyManage.jsx',
  'pages/AcademyReport.jsx',
  'pages/AuditTimelinePage.jsx',
  'pages/B2BApiDocs.jsx',
  'pages/ConflictQueuePage.jsx',
  'pages/CorporateContractApprovals.jsx',
  'pages/DataModelDashboard.jsx',
  'pages/GoLiveDashboardPage.jsx',
  'pages/HousekeepingStatusPage.jsx',
  'pages/IncidentDashboardPage.jsx',
  'pages/InventoryTransferHistory.jsx',
  'pages/LandingPage.jsx',
  'pages/POSExtensions.jsx',
  'pages/POSWaiterTerminal.jsx',
  'pages/PilotReadinessPage.jsx',
  'pages/ProcurementB2BTab.jsx',
  'pages/ProductionRolloutPage.jsx',
  'pages/RevenueAutopilotMonitor.jsx',
  'pages/ShiftPlannerPage.jsx',
  'pages/StaffManagement.jsx',
  'pages/StaffProfile.jsx',
  'pages/SupplierAuthPage.jsx'
];

const basePath = path.join(__dirname, '../src');
let newTranslations = {};

function slugify(text) {
  return text.trim()
    .toLowerCase()
    .replace(/[^a-z0-9ğüşöçı]/g, '_')
    .replace(/_+/g, '_')
    .substring(0, 30)
    .replace(/_$/, '');
}

function processFile(filePath) {
  const fullPath = path.join(basePath, filePath);
  if (!fs.existsSync(fullPath)) return;
  
  const code = fs.readFileSync(fullPath, 'utf8');
  if (code.includes('useTranslation')) return; // already has i18n
  
  const componentName = path.basename(filePath, '.jsx');
  let hasChanges = false;
  
  const ast = parser.parse(code, {
    sourceType: 'module',
    plugins: ['jsx']
  });

  let imported = false;
  let hookAdded = false;
  let mainComponent = null;

  traverse(ast, {
    ImportDeclaration(path) {
      if (path.node.source.value === 'react-i18next') {
        imported = true;
      }
    },
    FunctionDeclaration(path) {
      if (path.node.id && path.node.id.name === componentName) {
        mainComponent = path;
      }
    },
    VariableDeclarator(path) {
       if (path.node.id.name === componentName && (t.isArrowFunctionExpression(path.node.init) || t.isFunctionExpression(path.node.init))) {
           mainComponent = path.get('init');
       }
    },
    JSXText(path) {
      const text = path.node.value;
      if (text.trim().length > 1 && /[a-zA-ZğüşöçıĞÜŞÖÇİ]/.test(text)) {
        const slug = slugify(text);
        if (!slug) return;
        const key = `cm.pages_${componentName}.${slug}`;
        newTranslations[key] = text.trim();
        
        path.replaceWith(
          t.jsxExpressionContainer(
            t.callExpression(t.identifier('t'), [t.stringLiteral(key)])
          )
        );
        hasChanges = true;
      }
    },
    JSXAttribute(path) {
      if (['placeholder', 'title', 'label'].includes(path.node.name.name)) {
        if (t.isStringLiteral(path.node.value)) {
          const text = path.node.value.value;
          if (text.trim().length > 1 && /[a-zA-ZğüşöçıĞÜŞÖÇİ]/.test(text)) {
            const slug = slugify(text);
            if (!slug) return;
            const key = `cm.pages_${componentName}.${slug}`;
            newTranslations[key] = text.trim();
            
            path.node.value = t.jsxExpressionContainer(
              t.callExpression(t.identifier('t'), [t.stringLiteral(key)])
            );
            hasChanges = true;
          }
        }
      }
    }
  });

  if (hasChanges) {
    if (!imported) {
      const importDecl = t.importDeclaration(
        [t.importSpecifier(t.identifier('useTranslation'), t.identifier('useTranslation'))],
        t.stringLiteral('react-i18next')
      );
      ast.program.body.unshift(importDecl);
    }
    
    // Attempt to inject const { t } = useTranslation();
    // This is naive, relies on finding the main export or function.
    // Instead of doing it in AST which is risky, we can do it with regex after generating code.
    
    let outputCode = generate(ast, {}, code).code;
    
    // Regex inject const { t } = useTranslation();
    // Look for: export default function ComponentName() {
    // Or: const ComponentName = () => {
    
    outputCode = outputCode.replace(
      new RegExp(`(function\\s+${componentName}\\s*\\([^)]*\\)\\s*{)`),
      `$1\n  const { t } = useTranslation();`
    );
    outputCode = outputCode.replace(
      new RegExp(`(const\\s+${componentName}\\s*=\\s*\\([^)]*\\)\\s*=>\\s*{)`),
      `$1\n  const { t } = useTranslation();`
    );
    
    fs.writeFileSync(fullPath, outputCode, 'utf8');
    console.log(`Processed ${filePath}`);
  }
}

files.forEach(processFile);

fs.writeFileSync(path.join(__dirname, 'new_keys.json'), JSON.stringify(newTranslations, null, 2), 'utf8');
console.log('Saved new_keys.json');
