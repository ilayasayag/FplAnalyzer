/**
 * FPL Analyzer - State Management
 * 
 * Central state store for the application.
 * Persists to localStorage where appropriate.
 */

const State = {
    // Storage key prefix
    STORAGE_PREFIX: 'fpl_analyzer_',
    
    // Internal state
    _state: {
        initialized: false,
        currentGameweek: 21,
        statistics: null,
        leagueInfo: null,
        entries: [],
        teams: []
    },
    
    // ==========================================================================
    // Getters
    // ==========================================================================
    
    isInitialized() {
        return this._state.initialized;
    },
    
    getCurrentGameweek() {
        return this._state.currentGameweek;
    },
    
    getStatistics() {
        return this._state.statistics;
    },
    
    getLeagueInfo() {
        return this._state.leagueInfo;
    },
    
    getEntries() {
        return this._state.entries;
    },
    
    getEntryIds() {
        return this._state.entries.map(e => e.entry_id);
    },
    
    getTeams() {
        return this._state.teams;
    },
    
    // ==========================================================================
    // Setters
    // ==========================================================================
    
    setInitialized(value) {
        this._state.initialized = value;
        this._notifyChange('initialized');
    },
    
    setCurrentGameweek(gw) {
        this._state.currentGameweek = gw;
        this._save('currentGameweek', gw);
        this._notifyChange('currentGameweek');
    },
    
    setStatistics(stats) {
        this._state.statistics = stats;
        if (stats?.current_gameweek) {
            this._state.currentGameweek = stats.current_gameweek;
        }
        this._notifyChange('statistics');
    },
    
    setLeagueInfo(info) {
        this._state.leagueInfo = info;
        this._state.entries = info?.entries || [];
        if (info?.current_gameweek) {
            this._state.currentGameweek = info.current_gameweek;
        }
        this._notifyChange('leagueInfo');
        this._notifyChange('entries');
    },
    
    setTeams(teams) {
        this._state.teams = teams;
        this._notifyChange('teams');
    },
    
    // ==========================================================================
    // Persistence
    // ==========================================================================
    
    _save(key, value) {
        try {
            localStorage.setItem(this.STORAGE_PREFIX + key, JSON.stringify(value));
        } catch (e) {
            console.warn('Failed to save to localStorage:', e);
        }
    },
    
    _load(key, defaultValue = null) {
        try {
            const stored = localStorage.getItem(this.STORAGE_PREFIX + key);
            return stored ? JSON.parse(stored) : defaultValue;
        } catch (e) {
            console.warn('Failed to load from localStorage:', e);
            return defaultValue;
        }
    },
    
    // ==========================================================================
    // Change Notifications
    // ==========================================================================
    
    _listeners: {},
    
    /**
     * Subscribe to state changes
     * @param {string} key - State key to watch
     * @param {Function} callback - Called when key changes
     */
    subscribe(key, callback) {
        if (!this._listeners[key]) {
            this._listeners[key] = [];
        }
        this._listeners[key].push(callback);
    },
    
    /**
     * Unsubscribe from state changes
     */
    unsubscribe(key, callback) {
        if (this._listeners[key]) {
            this._listeners[key] = this._listeners[key].filter(cb => cb !== callback);
        }
    },
    
    _notifyChange(key) {
        if (this._listeners[key]) {
            this._listeners[key].forEach(cb => cb(this._state[key]));
        }
    },
    
    // ==========================================================================
    // Initialization
    // ==========================================================================
    
    async init() {
        // Load persisted values
        const savedGw = this._load('currentGameweek');
        if (savedGw) {
            this._state.currentGameweek = savedGw;
        }
        
        // Check API health to see if data is loaded
        try {
            const health = await FPL.health();
            this._state.initialized = health.initialized;
            
            if (health.initialized && health.data_loaded) {
                this._state.statistics = health.data_loaded;
                if (health.data_loaded.current_gameweek) {
                    this._state.currentGameweek = health.data_loaded.current_gameweek;
                }
                
                // Load league info
                await FPL.refreshLeagueInfo();
            }
        } catch (e) {
            console.warn('API not available:', e.message);
        }
        
        return this._state;
    }
};

// Make globally available
window.State = State;


