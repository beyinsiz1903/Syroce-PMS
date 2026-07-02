const fs = require('fs');
const path = require('path');
const parser = require('@babel/parser');
const traverse = require('@babel/traverse').default;
const generate = require('@babel/generator').default;
const t = require('@babel/types');

const sourceFile = process.argv[2];
const outDir = process.argv[3];
const prefix = process.argv[4] || '';

if (!sourceFile || !outDir) {
    console.error("Usage: node extract_tabs.js <source_file> <out_dir> [prefix]");
    process.exit(1);
}

const code = fs.readFileSync(sourceFile, 'utf8');

const ast = parser.parse(code, {
    sourceType: 'module',
    plugins: ['jsx', 'classProperties', 'optionalChaining', 'nullishCoalescingOperator']
});

let extractedComponents = [];

traverse(ast, {
    JSXElement(path) {
        if (t.isJSXIdentifier(path.node.openingElement.name, { name: 'TabsContent' })) {
            const valueAttr = path.node.openingElement.attributes.find(
                attr => t.isJSXAttribute(attr) && attr.name.name === 'value'
            );
            
            if (valueAttr && t.isStringLiteral(valueAttr.value)) {
                const tabValue = valueAttr.value.value;
                const compName = prefix + tabValue.charAt(0).toUpperCase() + tabValue.slice(1) + 'Tab';
                
                // Find unbound identifiers inside this JSX element
                let unbound = new Set();
                path.traverse({
                    Identifier(idPath) {
                        // Check if it's a reference and not bound in the local scope
                        if (idPath.isReferencedIdentifier()) {
                            // Ignore globals or standard React stuff
                            if (['React', 't', 'console', 'window', 'document', 'undefined', 'NaN', 'Math', 'JSON', 'Object', 'String', 'Array', 'Boolean', 'Number', 'Date', 'Promise', 'setTimeout', 'clearTimeout'].includes(idPath.node.name)) return;
                            
                            // Check if it has a binding in this scope or parent scopes
                            const binding = idPath.scope.getBinding(idPath.node.name);
                            if (binding) {
                                let isInside = false;
                                let current = binding.path;
                                while (current) {
                                    if (current === path) {
                                        isInside = true;
                                        break;
                                    }
                                    current = current.parentPath;
                                }
                                if (!isInside) {
                                    unbound.add(idPath.node.name);
                                }
                            } else {
                                // Add truly unbound (likely imported from UI components, lucide, etc)
                                unbound.add(idPath.node.name);
                            }
                        }
                    }
                });

                const propsList = Array.from(unbound);
                
                // Create the extracted component code
                const jsxCode = generate(path.node).code;
                
                const compCode = `import React from 'react';
import { useTranslation } from 'react-i18next';
// You may need to fix imports manually (Lucide icons, UI components)

export default function ${compName}({ ${propsList.join(', ')} }) {
    const { t } = useTranslation();
    return (
        ${jsxCode}
    );
}
`;
                extractedComponents.push({ name: compName, code: compCode, props: propsList });

                // Replace the original JSX element with <CompName {...props} />
                const attrs = propsList.map(prop => t.jsxAttribute(t.jsxIdentifier(prop), t.jsxExpressionContainer(t.identifier(prop))));
                
                const replacement = t.jsxElement(
                    t.jsxOpeningElement(t.jsxIdentifier(compName), attrs, true),
                    null,
                    [],
                    true
                );
                
                path.replaceWith(replacement);
                path.skip(); // Don't traverse inside the newly replaced element
            }
        }
    }
});

if (extractedComponents.length > 0) {
    // Generate imports for the main file
    const imports = extractedComponents.map(c => `import ${c.name} from './${c.name}';`).join('\n');
    
    let newMainCode = generate(ast, {}, code).code;
    
    // Inject imports after the last import
    const lastImportIndex = newMainCode.lastIndexOf('import ');
    if (lastImportIndex !== -1) {
        const nextNewline = newMainCode.indexOf('\n', lastImportIndex);
        newMainCode = newMainCode.slice(0, nextNewline + 1) + imports + '\n' + newMainCode.slice(nextNewline + 1);
    } else {
        newMainCode = imports + '\n' + newMainCode;
    }
    
    const baseName = path.basename(sourceFile);
    fs.writeFileSync(path.join(outDir, baseName), newMainCode, 'utf8');
    
    extractedComponents.forEach(c => {
        fs.writeFileSync(path.join(outDir, `${c.name}.jsx`), c.code, 'utf8');
        console.log(`Generated ${c.name}.jsx with props: ${c.props.join(', ')}`);
    });
    console.log(`Refactored ${sourceFile} successfully.`);
} else {
    console.log("No TabsContent found.");
}
