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

