const fs = require('fs');
const path = require('path');

// We try to require the babel parser from the local node_modules
let parser;
try {
  parser = require('@babel/parser');
} catch (e) {
  // If not present under @babel/parser directly, try to require babel-core's parser or similar
  try {
    parser = require(path.join(__dirname, '..', 'node_modules', 'acorn'));
  } catch (e2) {
    console.error("Neither @babel/parser nor Acorn was found in node_modules.");
    process.exit(1);
  }
}

const dir = path.join(__dirname, '..', 'draft_wc_design');
const files = fs.readdirSync(dir);

let anyFailed = false;

files.forEach(file => {
  if (file.endsWith('.jsx')) {
    const filePath = path.join(dir, file);
    const content = fs.readFileSync(filePath, 'utf8');
    
    try {
      if (parser.parse) {
        // If it's @babel/parser
        parser.parse(content, {
          sourceType: "module",
          plugins: ["jsx"]
        });
      } else {
        // If Acorn (needs acorn-jsx plugin to parse JSX, so we might get false alarms)
        parser.parse(content, { ecmaVersion: 2020 });
      }
      console.log(`✅ ${file}: Parsed successfully!`);
    } catch (err) {
      console.error(`❌ ${file}: Syntax Error at line ${err.loc ? err.loc.line : 'unknown'}, col ${err.loc ? err.loc.column : 'unknown'}`);
      console.error(`   Message: ${err.message}`);
      anyFailed = true;
    }
  }
});

if (!anyFailed) {
  console.log("\nAll JSX files compiled cleanly!");
} else {
  process.exit(1);
}
