/**
 * DataService - Smart data fetching with cache → DB → sync pattern
 * 
 * Handles:
 * 1. In-memory cache (fastest)
 * 2. Database queries via API (persistent)
 * 3. Sync from JSON files (manual update)
 */

const DataService = {
    // In-memory cache
    _cache: {
        players: null,
        teams: null,
        squads: null,
        ownedIds: null,
        freeAgents: {},
        league: null,
        entries: null,
        lastSync: null
    },
    
    // Cache expiry times (ms)
    _ttl: {
        players: 5 * 60 * 1000,      // 5 minutes
        teams: 10 * 60 * 1000,       // 10 minutes
        squads: 2 * 60 * 1000,       // 2 minutes (changes with transactions)
        ownedIds: 2 * 60 * 1000,     // 2 minutes
        freeAgents: 2 * 60 * 1000,   // 2 minutes
        league: 30 * 60 * 1000,      // 30 minutes
        entries: 30 * 60 * 1000      // 30 minutes
    },
    
    // Cache timestamps
    _cacheTime: {},
    
    // Status
    _dbAvailable: null,
    _lastSyncTime: null,
    
    /**
     * Check if cache is valid
     */
    _isCacheValid(key) {
        if (!this._cache[key]) return false;
        const cacheTime = this._cacheTime[key];
        if (!cacheTime) return false;
        return (Date.now() - cacheTime) < this._ttl[key];
    },
    
    /**
     * Set cache with timestamp
     */
    _setCache(key, data) {
        this._cache[key] = data;
        this._cacheTime[key] = Date.now();
    },
    
    /**
     * Clear all caches
     */
    clearCache() {
        for (const key of Object.keys(this._cache)) {
            this._cache[key] = null;
            this._cacheTime[key] = null;
        }
        console.log('[DataService] Cache cleared');
    },
    
    /**
     * Check if database is available and has data
     */
    async checkDbStatus() {
        try {
            const response = await fetch('/api/db/status');
            const data = await response.json();
            
            if (data.status === 'connected' && data.tables) {
                const hasData = data.tables.pl_players > 0;
                this._dbAvailable = hasData;
                console.log('[DataService] DB status:', hasData ? 'Available with data' : 'Empty');
                return { available: true, hasData, tables: data.tables };
            }
            
            this._dbAvailable = false;
            return { available: false, hasData: false };
        } catch (e) {
            console.warn('[DataService] DB check failed:', e);
            this._dbAvailable = false;
            return { available: false, hasData: false, error: e.message };
        }
    },
    
    /**
     * Sync database from newest JSON file
     * 
     * Calls the new /api/auto-load endpoint which:
     * 1. Finds the newest fpl_league_data_*.json file
     * 2. Imports it into DuckDB
     * 3. Processes transactions to reconstruct current squads
     * 4. Returns import statistics
     */
    async syncFromFile() {
        console.log('[DataService] Starting sync from newest file...');
        
        try {
            // Step 1: Load the newest JSON file
            const loadResponse = await fetch('/api/auto-load', { 
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const loadData = await loadResponse.json();
            
            if (!loadData.success) {
                console.error('[DataService] Auto-load failed:', loadData.error);
                return { 
                    success: false, 
                    error: loadData.error || 'Failed to load file' 
                };
            }
            
            console.log('[DataService] Successfully loaded:', loadData.filename);
            
            // Step 2: Import the data into DuckDB
            const importResponse = await fetch('/api/db/import', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(loadData.data)
            });
            
            const importResult = await importResponse.json();
            
            if (!importResult.success) {
                console.error('[DataService] DB import failed:', importResult.error);
                return {
                    success: false,
                    error: importResult.error || 'Failed to import into database'
                };
            }
            
            console.log('[DataService] Import stats:', importResult);
            
            // Clear cache to force fresh data
            this.clearCache();
            this._lastSyncTime = Date.now();
            this._dbAvailable = true;
            
            return {
                success: true,
                filename: loadData.filename,
                message: `Imported ${importResult.players_imported} players, ${importResult.teams_imported} teams`,
                imported: {
                    players: importResult.players_imported,
                    teams: importResult.teams_imported,
                    squads: importResult.squads_imported,
                    gameweeks: importResult.gameweeks_imported,
                    entries: importResult.entries_imported,
                    transactions: importResult.transactions_imported
                },
                predictor_initialized: loadData.predictor_initialized || false
            };
        } catch (e) {
            console.error('[DataService] Sync failed:', e);
            return { success: false, error: e.message };
        }
    },
    
    /**
     * Get all players - cache → DB → empty
     */
    async getPlayers(filters = {}) {
        const cacheKey = 'players';
        
        // Check cache
        if (this._isCacheValid(cacheKey) && !filters.position && !filters.team_id) {
            console.log('[DataService] Players from cache');
            return this._cache[cacheKey];
        }
        
        // Try database
        if (this._dbAvailable !== false) {
            try {
                const params = new URLSearchParams();
                if (filters.position) params.append('position', filters.position);
                if (filters.team_id) params.append('team_id', filters.team_id);
                if (filters.limit) params.append('limit', filters.limit);
                
                const response = await fetch(`/api/db/players?${params}`);
                const players = await response.json();
                
                if (players && players.length > 0) {
                    if (!filters.position && !filters.team_id) {
                        this._setCache(cacheKey, players);
                    }
                    console.log('[DataService] Players from DB:', players.length);
                    return players;
                }
            } catch (e) {
                console.warn('[DataService] DB players fetch failed:', e);
            }
        }
        
        // Fallback to global variable (local data)
        if (typeof importedBootstrap !== 'undefined' && importedBootstrap?.elements) {
            console.log('[DataService] Players from local');
            return importedBootstrap.elements;
        }
        
        return [];
    },
    
    /**
     * Get a single player with history
     */
    async getPlayer(playerId, includeHistory = true) {
        // Try database first
        if (this._dbAvailable !== false) {
            try {
                const response = await fetch(`/api/db/player/${playerId}?history=${includeHistory}`);
                if (response.ok) {
                    const player = await response.json();
                    if (player && player.id) {
                        console.log('[DataService] Player from DB:', player.web_name);
                        return player;
                    }
                }
            } catch (e) {
                console.warn('[DataService] DB player fetch failed:', e);
            }
        }
        
        // Fallback to local
        if (typeof importedBootstrap !== 'undefined') {
            const bs = importedBootstrap?.elements?.find(e => e.id === playerId);
            const details = typeof importedPlayerDetails !== 'undefined' ? importedPlayerDetails?.[playerId] : null;
            if (bs) {
                return {
                    ...bs,
                    history: details?.history || []
                };
            }
        }
        
        return null;
    },
    
    /**
     * Get teams - cache → DB → local
     */
    async getTeams() {
        const cacheKey = 'teams';
        
        if (this._isCacheValid(cacheKey)) {
            console.log('[DataService] Teams from cache');
            return this._cache[cacheKey];
        }
        
        if (this._dbAvailable !== false) {
            try {
                const response = await fetch('/api/db/teams');
                const teams = await response.json();
                if (teams && teams.length > 0) {
                    this._setCache(cacheKey, teams);
                    console.log('[DataService] Teams from DB:', teams.length);
                    return teams;
                }
            } catch (e) {
                console.warn('[DataService] DB teams fetch failed:', e);
            }
        }
        
        if (typeof importedBootstrap !== 'undefined' && importedBootstrap?.teams) {
            console.log('[DataService] Teams from local');
            return importedBootstrap.teams;
        }
        
        return [];
    },
    
    /**
     * Get owned player IDs - critical for free agents
     */
    async getOwnedIds(gameweek = null) {
        const cacheKey = 'ownedIds';
        
        if (this._isCacheValid(cacheKey)) {
            console.log('[DataService] OwnedIds from cache');
            return this._cache[cacheKey];
        }
        
        if (this._dbAvailable !== false) {
            try {
                const params = gameweek ? `?gameweek=${gameweek}` : '';
                const response = await fetch(`/api/db/owned-ids${params}`);
                const data = await response.json();
                if (data.owned_ids) {
                    const ownedSet = new Set(data.owned_ids);
                    this._setCache(cacheKey, ownedSet);
                    console.log('[DataService] OwnedIds from DB:', ownedSet.size);
                    return ownedSet;
                }
            } catch (e) {
                console.warn('[DataService] DB owned-ids fetch failed:', e);
            }
        }
        
        // Fallback to local calculation
        if (typeof importedLeagueData !== 'undefined' && importedLeagueData?.squads) {
            const owned = new Set();
            Object.values(importedLeagueData.squads).forEach(squad => {
                const picks = squad?.picks || [];
                picks.forEach(p => {
                    if (p.element) owned.add(p.element);
                });
            });
            console.log('[DataService] OwnedIds from local:', owned.size);
            return owned;
        }
        
        return new Set();
    },
    
    /**
     * Get free agents - cache → DB
     */
    async getFreeAgents(gameweek, position = null, limit = 50) {
        const cacheKey = `freeAgents_${gameweek}_${position || 'all'}`;
        
        // Check cache
        if (this._cache.freeAgents[cacheKey] && 
            (Date.now() - (this._cacheTime[cacheKey] || 0)) < this._ttl.freeAgents) {
            console.log('[DataService] FreeAgents from cache');
            return this._cache.freeAgents[cacheKey];
        }
        
        if (this._dbAvailable !== false) {
            try {
                const params = new URLSearchParams({ gameweek, limit });
                if (position) params.append('position', position);
                
                const response = await fetch(`/api/db/free-agents?${params}`);
                const data = await response.json();
                
                if (data.players && data.players.length > 0) {
                    this._cache.freeAgents[cacheKey] = data.players;
                    this._cacheTime[cacheKey] = Date.now();
                    console.log('[DataService] FreeAgents from DB:', data.players.length);
                    return data.players;
                }
            } catch (e) {
                console.warn('[DataService] DB free-agents fetch failed:', e);
            }
        }
        
        return null; // Signal to use local calculation
    },
    
    /**
     * Get league info
     */
    async getLeague() {
        const cacheKey = 'league';
        
        if (this._isCacheValid(cacheKey)) {
            return this._cache[cacheKey];
        }
        
        if (this._dbAvailable !== false) {
            try {
                const response = await fetch('/api/db/league');
                if (response.ok) {
                    const league = await response.json();
                    if (league && league.id) {
                        this._setCache(cacheKey, league);
                        return league;
                    }
                }
            } catch (e) {
                console.warn('[DataService] DB league fetch failed:', e);
            }
        }
        
        if (typeof importedLeagueData !== 'undefined') {
            return importedLeagueData?.league;
        }
        
        return null;
    },
    
    /**
     * Get squads
     */
    async getSquads(gameweek = null) {
        const cacheKey = 'squads';
        
        if (this._isCacheValid(cacheKey)) {
            return this._cache[cacheKey];
        }
        
        if (this._dbAvailable !== false) {
            try {
                const params = gameweek ? `?gameweek=${gameweek}` : '';
                const response = await fetch(`/api/db/squads${params}`);
                const data = await response.json();
                if (data.squads) {
                    this._setCache(cacheKey, data.squads);
                    return data.squads;
                }
            } catch (e) {
                console.warn('[DataService] DB squads fetch failed:', e);
            }
        }
        
        if (typeof importedLeagueData !== 'undefined') {
            return importedLeagueData?.squads;
        }
        
        return {};
    },
    
    /**
     * Get league entries (FPL teams)
     */
    async getEntries() {
        const cacheKey = 'entries';
        
        if (this._isCacheValid(cacheKey)) {
            return this._cache[cacheKey];
        }
        
        if (this._dbAvailable !== false) {
            try {
                const response = await fetch('/api/db/entries');
                const entries = await response.json();
                if (entries && entries.length > 0) {
                    this._setCache(cacheKey, entries);
                    return entries;
                }
            } catch (e) {
                console.warn('[DataService] DB entries fetch failed:', e);
            }
        }
        
        if (typeof importedLeagueData !== 'undefined') {
            return importedLeagueData?.league?.league_entries || [];
        }
        
        return [];
    },
    
    /**
     * Get last sync time
     */
    getLastSyncTime() {
        return this._lastSyncTime;
    },
    
    /**
     * Initialize - check DB status
     */
    async init() {
        console.log('[DataService] Initializing...');
        const status = await this.checkDbStatus();
        
        if (status.hasData) {
            console.log('[DataService] DB has data, ready to use');
        } else {
            console.log('[DataService] DB empty, will use local data or need sync');
        }
        
        return status;
    }
};

// Make globally available
window.DataService = DataService;

console.log('[DataService] Module loaded');
