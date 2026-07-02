const fs = require('fs');
const path = require('path');
const babel = require('@babel/core');
const parser = require('@babel/parser');
const traverse = require('@babel/traverse').default;
const generate = require('@babel/generator').default;
const t = require('@babel/types');

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
  
  const ast = parser.parse(code, {
    sourceType: 'module',
    plugins: ['jsx']
  });

  let changed = false;

  const injectT = (path) => {
    // Check if body is block statement
    if (!t.isBlockStatement(path.node.body)) {
      // Convert implicit return to block
      path.node.body = t.blockStatement([t.returnStatement(path.node.body)]);
    }

    // Check if it already has const { t } = useTranslation();
    const hasT = path.node.body.body.some(stmt => {
      if (t.isVariableDeclaration(stmt)) {
        return stmt.declarations.some(decl => {
          if (t.isObjectPattern(decl.id)) {
            return decl.id.properties.some(prop => prop.key && prop.key.name === 't');
          }
          return false;
        });
      }
      return false;
    });

    if (!hasT) {
      // Find if this function actually uses t()
      let usesT = false;
      path.traverse({
        CallExpression(callPath) {
          if (t.isIdentifier(callPath.node.callee, { name: 't' })) {
            usesT = true;
            callPath.stop();
          }
        }
      });

      if (usesT) {
        const useTranslationDecl = t.variableDeclaration('const', [
          t.variableDeclarator(
            t.objectPattern([t.objectProperty(t.identifier('t'), t.identifier('t'), false, true)]),
            t.callExpression(t.identifier('useTranslation'), [])
          )
        ]);
        path.node.body.body.unshift(useTranslationDecl);
        changed = true;
      }
    }
  };

  traverse(ast, {
    FunctionDeclaration(path) {
      injectT(path);
    },
    ArrowFunctionExpression(path) {
      injectT(path);
    },
    FunctionExpression(path) {
      injectT(path);
    }
  });

  if (changed) {
    const output = generate(ast, {}, code).code;
    fs.writeFileSync(p, output, 'utf8');
    console.log(`Fixed ${file}`);
  }
}
