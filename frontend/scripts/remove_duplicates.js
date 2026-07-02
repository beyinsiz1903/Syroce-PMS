const fs = require('fs');
const path = require('path');

const dirs = ['hr', 'settings', 'maintenance'];
const basePath = '/Users/syroce/Documents/GitHub/SyrocePMS/frontend/src/pages';

dirs.forEach(dir => {
    const dirPath = path.join(basePath, dir);
    if (!fs.existsSync(dirPath)) return;
    
    fs.readdirSync(dirPath).forEach(file => {
        if (file.endsWith('.jsx') && file !== 'index.jsx') {
            const filePath = path.join(dirPath, file);
            let content = fs.readFileSync(filePath, 'utf8');
            
            // Remove the duplicate imports added by the extraction script
            content = content.replace("import React from 'react';\nimport { useTranslation } from 'react-i18next';\n", "");
            
            fs.writeFileSync(filePath, content, 'utf8');
            console.log("Fixed duplicates in", file);
        }
    });
});
