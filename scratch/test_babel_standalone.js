const fs = require('fs');
const path = require('path');
const https = require('https');
const vm = require('vm');

// Fetch Babel Standalone from CDN
console.log("Fetching Babel Standalone 7.29.0 from CDN...");
const babelUrl = 'https://unpkg.com/@babel/standalone@7.29.0/babel.min.js';

https.get(babelUrl, (res) => {
  let data = '';
  res.on('data', (chunk) => data += chunk);
  res.on('end', () => {
    console.log("Babel Standalone downloaded successfully. Loading environment...");
    
    // Create a context with window and global mock
    const context = {
      window: {},
      console: console,
      exports: {},
      module: { exports: {} }
    };
    context.global = context;
    vm.createContext(context);
    
    // Run Babel in context
    vm.runInContext(data, context);
    
    let Babel = context.Babel || (context.window && context.window.Babel) || context.exports?.Babel || context.module?.exports?.Babel;
    
    if (!Babel) {
      // Find any key that might be Babel
      for (const k in context) {
        if (context[k] && typeof context[k] === 'object' && context[k].transform) {
          Babel = context[k];
          break;
        }
      }
    }
    
    if (!Babel) {
      console.error("Failed to load Babel Standalone. Available keys in context:", Object.keys(context));
      process.exit(1);
    }
    
    console.log("Babel Standalone loaded successfully. Scanning JSX files...");
    
    const dir = path.join(__dirname, '..', 'draft_wc_design');
    const files = fs.readdirSync(dir);
    let anyFailed = false;
    
    files.forEach(file => {
      if (file.endsWith('.jsx')) {
        const filePath = path.join(dir, file);
        const code = fs.readFileSync(filePath, 'utf8');
        
        try {
          // Compile using the same presets Babel Standalone uses for type="text/babel"
          Babel.transform(code, {
            presets: ['react'],
            filename: file
          });
          console.log(`✅ ${file}: Compiled cleanly with Babel Standalone!`);
        } catch (err) {
          console.error(`\n❌ ${file}: Babel Standalone Compilation Error!`);
          console.error(err.message);
          anyFailed = true;
        }
      }
    });
    
    if (!anyFailed) {
      console.log("\nAll JSX files compiled cleanly with Babel Standalone!");
    } else {
      process.exit(1);
    }
  });
}).on('error', (err) => {
  console.error("Failed to download Babel Standalone:", err.message);
  process.exit(1);
});
