/**
 * FPL Analyzer - Main Application
 * 
 * Entry point that initializes all modules and handles tab navigation.
 */

const App = {
    // Track current tab
    currentTab: 'import',
    
    // ==========================================================================
    // Initialization
    // ==========================================================================
    
    async init() {
        console.log('FPL Analyzer starting...');
        
        // Initialize state first
        await State.init();
        
        // Check if database has data, auto-sync if needed
        await this.checkAndAutoSync();
        
        // Setup tab navigation
        this.setupTabs();
        
        // Initialize UI modules
        Fixtures.init();
        Predictions.init();
        Squad.init();
        H2H.init();
        Trades.init();
        
        // Update data status
        if (State.isInitialized()) {
            FPL.updateDataStatus(State.getStatistics());
        } else {
            FPL.updateDataStatus(null);
        }
        
        console.log('FPL Analyzer ready!');
    },
    
    /**
     * Check database status and auto-sync if no data found
     */
    async checkAndAutoSync() {
        console.log('[App] Checking database status...');
        
        try {
            // Check if database has data
            const response = await fetch('/api/auto-load', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const result = await response.json();
            
            if (result.success) {
                console.log(`[App] Auto-loaded: ${result.filename}`);
                
                // Show success message
                const statusDiv = document.getElementById('dataStatus');
                if (statusDiv) {
                    statusDiv.textContent = `✅ Loaded ${result.filename}`;
                    statusDiv.className = 'alert success';
                    statusDiv.style.display = 'block';
                    
                    // Hide after 5 seconds
                    setTimeout(() => {
                        statusDiv.style.display = 'none';
                    }, 5000);
                }
                
                // Update state
                State.setInitialized(true);
            } else {
                console.warn('[App] Auto-load failed:', result.error);
                
                // Show warning
                const statusDiv = document.getElementById('dataStatus');
                if (statusDiv) {
                    statusDiv.textContent = '⚠️ No FPL data found. Please import data manually.';
                    statusDiv.className = 'alert warning';
                    statusDiv.style.display = 'block';
                }
            }
        } catch (error) {
            console.error('[App] Auto-sync error:', error);
            
            // Show error
            const statusDiv = document.getElementById('dataStatus');
            if (statusDiv) {
                statusDiv.textContent = '❌ Failed to load data. Please import manually.';
                statusDiv.className = 'alert error';
                statusDiv.style.display = 'block';
            }
        }
    },
    
    // ==========================================================================
    // Tab Navigation
    // ==========================================================================
    
    setupTabs() {
        // Get all tab buttons
        const tabBtns = document.querySelectorAll('.tab-btn');
        
        tabBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const tabId = btn.dataset.tab;
                this.switchTab(tabId);
            });
        });
        
        // Show initial tab
        this.switchTab('import');
    },
    
    /**
     * Switch to a specific tab
     * @param {string} tabId - Tab identifier
     */
    switchTab(tabId) {
        // Update button states
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabId);
        });
        
        // Update content visibility
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.toggle('active', content.id === `tab-${tabId}`);
        });
        
        this.currentTab = tabId;
        
        // Tab-specific initialization
        this.onTabSwitch(tabId);
    },
    
    /**
     * Handle tab switch - load data as needed
     */
    onTabSwitch(tabId) {
        switch (tabId) {
            case 'fixtures':
                // Fixtures loads on init, but could refresh here
                break;
                
            case 'predictions':
                // Refresh entry dropdowns
                Predictions.populateDropdowns();
                break;
                
            case 'squad':
                Squad.populateDropdowns();
                break;
                
            case 'h2h':
                H2H.populateDropdowns();
                break;
                
            case 'trades':
                Trades.populateDropdowns();
                break;
        }
    }
};

// ==========================================================================
// DOM Ready
// ==========================================================================

document.addEventListener('DOMContentLoaded', () => {
    App.init();
});

// Make globally available
window.App = App;


