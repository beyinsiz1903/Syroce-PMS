const fs = require('fs');
const path = require('path');
const babel = require('@babel/core');
const parser = require('@babel/parser');
const traverse = require('@babel/traverse').default;
const generate = require('@babel/generator').default;
const t = require('@babel/types');

function findFiles(dir, ext) {
  let results = [];
  const list = fs.readdirSync(dir);
  list.forEach(file => {
    file = path.join(dir, file);
    const stat = fs.statSync(file);
    if (stat && stat.isDirectory()) {
      if (!file.includes('node_modules')) {
          results = results.concat(findFiles(file, ext));
      }
    } else {
      if (file.endsWith(ext)) results.push(file);
    }
  });
  return results;
}

const files = findFiles(path.join(__dirname, '../src'), '.jsx');

let totalFixed = 0;

files.forEach(file => {
  const code = fs.readFileSync(file, 'utf8');
  if (!code.includes('key={i}') && !code.includes('key={index}')) return;

  try {
      const ast = parser.parse(code, {
        sourceType: 'module',
        plugins: ['jsx', 'classProperties', 'optionalChaining', 'nullishCoalescingOperator']
      });

      let changed = false;

      traverse(ast, {
        CallExpression(path) {
          // Look for .map() calls
          if (
            t.isMemberExpression(path.node.callee) &&
            t.isIdentifier(path.node.callee.property, { name: 'map' }) &&
            path.node.arguments.length > 0
          ) {
            const callback = path.node.arguments[0];
            if (t.isArrowFunctionExpression(callback) || t.isFunctionExpression(callback)) {
              const params = callback.params;
              // params[0] is the item, params[1] is the index
              if (params.length > 0) {
                const itemName = t.isIdentifier(params[0]) ? params[0].name : (t.isObjectPattern(params[0]) ? 'item' : 'item');
                const indexName = params.length > 1 && t.isIdentifier(params[1]) ? params[1].name : null;

                if (indexName && (indexName === 'i' || indexName === 'index')) {
                  // Traverse inside the callback to find JSXElements with key={indexName}
                  path.traverse({
                    JSXAttribute(attrPath) {
                      if (attrPath.node.name.name === 'key') {
                        if (
                          t.isJSXExpressionContainer(attrPath.node.value) &&
                          t.isIdentifier(attrPath.node.value.expression, { name: indexName })
                        ) {
                          // Change to key={itemName.id || indexName}
                          // Wait, if itemName is an object destructuring like { id, name }, itemName would be 'item' here which is incorrect
                          // Let's use `${indexName}-${Math.random()}` for destructuring or fallback
                          let uidExpr;
                          if (t.isIdentifier(params[0])) {
                              uidExpr = t.logicalExpression(
                                '||',
                                t.memberExpression(t.identifier(itemName), t.identifier('id')),
                                t.identifier(indexName)
                              );
                          } else {
                              // If it's destructured, we just use id || indexName if id is extracted, else fallback
                              uidExpr = t.identifier(indexName); // Keep index to be safe if destructured, or use something else.
                              // For simplicity, let's just do `id || indexName` and hope id is defined if destructured? No.
                              // Let's just use `indexName` if destructured unless we can do better.
                          }
                          
                          if (t.isIdentifier(params[0])) {
                              attrPath.node.value.expression = uidExpr;
                              changed = true;
                              totalFixed++;
                          }
                        }
                      }
                    }
                  });
                }
              }
            }
          }
        }
      });

      if (changed) {
        const output = generate(ast, {}, code).code;
        fs.writeFileSync(file, output, 'utf8');
        console.log(`Fixed keys in ${file}`);
      }
  } catch (e) {
      console.log(`Failed to parse ${file}: ${e.message}`);
  }
});

console.log(`Total fixed: ${totalFixed}`);
