const fs = require('fs');
const path = require('path');
const vm = require('vm');

const dir = path.join(__dirname, '..', 'draft_wc_design');
const files = fs.readdirSync(dir);

let hasErrors = false;

files.forEach(file => {
  if (file.endsWith('.jsx')) {
    const filePath = path.join(dir, file);
    const code = fs.readFileSync(filePath, 'utf8');
    
    // We replace JSX tag syntax with simple strings/comments or we use babel if available,
    // but first let's try a simple parse or look for obvious syntax errors, 
    // or parse using acorn/babel if present in node_modules!
    console.log(`Checking ${file}...`);
    try {
      // Let's see if we can parse JSX. Standard vm.Script will fail on JSX tags like <div />.
      // So we check if we can run a simple regex check or use an available parser in node_modules.
      // Let's find out if there's a parser in node_modules.
      const hasBabel = fs.existsSync(path.join(__dirname, '..', 'node_modules', '@babel'));
      if (hasBabel) {
        // Parse with babel if possible
        console.log(`  (Using local babel parser)`);
      }
    } catch (e) {
      console.error(`Error in ${file}:`, e.message);
      hasErrors = true;
    }
  }
});
