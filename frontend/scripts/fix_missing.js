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
            
            // Re-add useTranslation
            if (!content.includes('import { useTranslation }')) {
                content = "import { useTranslation } from 'react-i18next';\n" + content;
            }
            
            if (file === 'SettingsPlanTab.jsx') {
                if (!content.includes('const PlanIcon')) {
                    content = content.replace("export default function SettingsPlanTab({", "export default function SettingsPlanTab({");
                    content = content.replace("const { t } = useTranslation();", "const { t } = useTranslation();\n    const PlanIcon = currentPlan.icon;");
                }
            }
            
            fs.writeFileSync(filePath, content, 'utf8');
            console.log("Added useTranslation to", file);
        }
    });
});
