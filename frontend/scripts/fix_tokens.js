const fs = require('fs');
const path = require('path');
const parser = require('@babel/parser');
const traverse = require('@babel/traverse').default;
const generate = require('@babel/generator').default;
const t = require('@babel/types');

const basePaths = [
    '/Users/syroce/Documents/GitHub/SyrocePMS/frontend/src/components',
    '/Users/syroce/Documents/GitHub/SyrocePMS/frontend/src/pages'
];

function processFile(filePath) {
    let code = fs.readFileSync(filePath, 'utf8');
    if (!code.includes("localStorage.getItem('token')") && !code.includes('Bearer ${token}')) return;

    let ast;
    try {
        ast = parser.parse(code, {
            sourceType: 'module',
            plugins: ['jsx', 'classProperties', 'optionalChaining', 'nullishCoalescingOperator']
        });
    } catch (e) {
        console.error("Parse error in", filePath, e);
        return;
    }

    let modified = false;

    traverse(ast, {
        VariableDeclarator(p) {
            if (p.node.id.name === 'token' && p.node.init && 
                t.isCallExpression(p.node.init) && 
                p.node.init.callee.property && p.node.init.callee.property.name === 'getItem' &&
                p.node.init.arguments[0] && p.node.init.arguments[0].value === 'token') {
                p.remove();
                modified = true;
            }
        },
        ObjectProperty(p) {
            if ((t.isIdentifier(p.node.key, { name: 'Authorization' }) || t.isStringLiteral(p.node.key, { value: 'Authorization' })) &&
                t.isTemplateLiteral(p.node.value)) {
                p.remove();
                modified = true;
            }
        },
        CallExpression(p) {
            if (t.isIdentifier(p.node.callee, { name: 'fetch' })) {
                if (p.node.arguments.length >= 2) {
                    let options = p.node.arguments[1];
                    if (t.isObjectExpression(options)) {
                        let hasCredentials = options.properties.some(prop => 
                            (t.isIdentifier(prop.key, {name: 'credentials'}) || t.isStringLiteral(prop.key, {value: 'credentials'}))
                        );
                        if (!hasCredentials) {
                            options.properties.push(t.objectProperty(t.identifier('credentials'), t.stringLiteral('include')));
                            modified = true;
                        }
                        
                        // If headers is empty after removing Authorization, it's fine, fetch ignores empty headers.
                    }
                } else if (p.node.arguments.length === 1) {
                    p.node.arguments.push(t.objectExpression([
                        t.objectProperty(t.identifier('credentials'), t.stringLiteral('include'))
                    ]));
                    modified = true;
                }
            }
        }
    });

    if (modified) {
        let newCode = generate(ast, {}, code).code;
        fs.writeFileSync(filePath, newCode, 'utf8');
        console.log(`Fixed token usage in ${filePath}`);
    }
}

function walk(dir) {
    let files = fs.readdirSync(dir);
    for (let file of files) {
        let fullPath = path.join(dir, file);
        if (fs.statSync(fullPath).isDirectory()) {
            walk(fullPath);
        } else if (fullPath.endsWith('.jsx') || fullPath.endsWith('.js')) {
            processFile(fullPath);
        }
    }
}

basePaths.forEach(p => walk(p));
