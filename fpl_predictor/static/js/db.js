/**
 * FPLDB - Frontend Database Client
 * 
 * Provides a JavaScript interface to the DuckDB-backed API.
 * Replaces direct access to global variables with API calls.
 */

const FPLDB = {
    baseUrl: '/api/db',
    
    // Cache for frequently accessed data
    _cache: new Map(),
    _cacheExpiry: new Map(),
    
    /**
     * Internal fetch helper with error handling
     */
    async _fetch(endpoint, options = {}) {
        try {
            const url = `${this.baseUrl}${endpoint}`;
            const response = await fetch(url, {
                ...options,
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            });
            
            if (!response.ok) {
                const error = await response.json().catch(() => ({ error: response.statusText }));
                throw new Error(error.error || error.message || `HTTP ${response.status}`);
            }
            
            return response.json();
        } catch (error) {
            console.error(`[FPLDB] Error fetching ${endpoint}:`, error);
            throw error;
        }
    },
    
    /**
     * Get with caching support
     */
    async _cachedFetch(endpoint, ttlSeconds = 60) {
        const cacheKey = endpoint;
        const now = Date.now();
        
        // Check cache
        if (this._cache.has(cacheKey)) {
            const expiry = this._cacheExpiry.get(cacheKey);
            if (expiry > now) {
                return this._cache.get(cacheKey);
            }
        }
        
        // Fetch and cache
        const data = await this._fetch(endpoint);
        this._cache.set(cacheKey, data);
        this._cacheExpiry.set(cacheKey, now + (ttlSeconds * 1000));
        
        return data;
    },
    
    /**
     * Clear local cache
     */
    clearCache() {
        this._cache.clear();
        this._cacheExpiry.clear();
    },
    
    // =========================================================================
    // Database Status
    // =========================================================================
    
    /**
     * Get database status and statistics
     */
    async getStatus() {
        return this._fetch('/status');
    },
    
    /**
     * Import JSON data into the database
     */
    async importData(jsonData) {
        return this._fetch('/import', {
            method: 'POST',
            body: JSON.stringify(jsonData)
        });
    },
    
    // =========================================================================
    // Players
    // =========================================================================
    
    /**
     * Get all players with optional filters
     * @param {Object} filters - { position, team_id, status, limit }
     */
    async getPlayers(filters = {}) {
        const params = new URLSearchParams();
        if (filters.position) params.append('position', filters.position);
        if (filters.team_id) params.append('team_id', filters.team_id);
        if (filters.status) params.append('status', filters.status);
        if (filters.limit) params.append('limit', filters.limit);
        
        const query = params.toString();
        return this._fetch(`/players${query ? '?' + query : ''}`);
    },
    
    /**
     * Get a single player with full details
     * @param {number} playerId
     * @param {boolean} includeHistory - Include gameweek history
     */
    async getPlayer(playerId, includeHistory = true) {
        return this._fetch(`/player/${playerId}?history=${includeHistory}`);
    },
    
    /**
     * Get player performance by opponent batch
     */
    async getPlayerVsBatches(playerId) {
        return this._fetch(`/player/${playerId}/vs-batches`);
    },
    
    /**
     * Get player recent form
     */
    async getPlayerForm(playerId, games = 5) {
        return this._fetch(`/player/${playerId}/form?games=${games}`);
    },
    
    /**
     * Search players by name
     */
    async searchPlayers(query, limit = 20) {
        return this._fetch(`/players/search?q=${encodeURIComponent(query)}&limit=${limit}`);
    },
    
    // =========================================================================
    // Teams
    // =========================================================================
    
    /**
     * Get all teams with standings
     */
    async getTeams() {
        return this._cachedFetch('/teams', 300); // Cache for 5 minutes
    },
    
    /**
     * Get a single team
     */
    async getTeam(teamId) {
        return this._fetch(`/team/${teamId}`);
    },
    
    /**
     * Get team venue stats (home vs away performance)
     */
    async getTeamVenueStats(teamId) {
        return this._fetch(`/team/${teamId}/venue-stats`);
    },
    
    /**
     * Get current PL standings
     */
    async getStandings() {
        return this._cachedFetch('/standings', 300);
    },
    
    // =========================================================================
    // Squads & Ownership
    // =========================================================================
    
    /**
     * Get all squads for a gameweek
     */
    async getSquads(gameweek = null) {
        const params = gameweek ? `?gameweek=${gameweek}` : '';
        return this._fetch(`/squads${params}`);
    },
    
    /**
     * Get a single squad
     */
    async getSquad(entryId, gameweek = null) {
        const params = gameweek ? `?gameweek=${gameweek}` : '';
        return this._fetch(`/squad/${entryId}${params}`);
    },
    
    /**
     * Get all owned player IDs
     * This is the KEY method for determining free agents!
     */
    async getOwnedIds(gameweek = null) {
        const params = gameweek ? `?gameweek=${gameweek}` : '';
        const result = await this._fetch(`/owned-ids${params}`);
        return new Set(result.owned_ids || []);
    },
    
    // =========================================================================
    // Free Agents
    // =========================================================================
    
    /**
     * Get free agents (unowned players)
     * This properly filters out owned players using the database!
     */
    async getFreeAgents(gameweek = null, position = null, limit = 50) {
        const params = new URLSearchParams();
        if (gameweek) params.append('gameweek', gameweek);
        if (position) params.append('position', position);
        params.append('limit', limit);
        
        return this._fetch(`/free-agents?${params}`);
    },
    
    /**
     * Get top free agents by position
     */
    async getFreeAgentsByPosition(gameweek = null, perPosition = 3) {
        const params = new URLSearchParams();
        if (gameweek) params.append('gameweek', gameweek);
        params.append('per_position', perPosition);
        
        return this._fetch(`/free-agents/by-position?${params}`);
    },
    
    // =========================================================================
    // League
    // =========================================================================
    
    /**
     * Get league info
     */
    async getLeague() {
        return this._cachedFetch('/league', 300);
    },
    
    /**
     * Get all league entries
     */
    async getEntries() {
        return this._cachedFetch('/entries', 300);
    },
    
    /**
     * Get H2H matches
     */
    async getMatches(gameweek = null) {
        const params = gameweek ? `?gameweek=${gameweek}` : '';
        return this._fetch(`/matches${params}`);
    },
    
    /**
     * Get transactions
     */
    async getTransactions(gameweek = null, entryId = null) {
        const params = new URLSearchParams();
        if (gameweek) params.append('gameweek', gameweek);
        if (entryId) params.append('entry_id', entryId);
        
        const query = params.toString();
        return this._fetch(`/transactions${query ? '?' + query : ''}`);
    },
    
    // =========================================================================
    // Fixtures
    // =========================================================================
    
    /**
     * Get PL fixtures
     */
    async getFixtures(gameweek = null, finished = null) {
        const params = new URLSearchParams();
        if (gameweek) params.append('gameweek', gameweek);
        if (finished !== null) params.append('finished', finished);
        
        const query = params.toString();
        return this._fetch(`/fixtures${query ? '?' + query : ''}`);
    },
    
    /**
     * Get FDR fixture grid
     */
    async getFixtureGrid(gwStart = 21, gwEnd = 38) {
        return this._fetch(`/fixtures/grid?gw_start=${gwStart}&gw_end=${gwEnd}`);
    },
    
    /**
     * Get fixtures for a specific team
     */
    async getTeamFixtures(teamId, gwStart = 21, gwEnd = 38) {
        return this._fetch(`/fixtures/team/${teamId}?gw_start=${gwStart}&gw_end=${gwEnd}`);
    },
    
    // =========================================================================
    // Predictions & Cache
    // =========================================================================
    
    /**
     * Get cached predictions for a gameweek
     */
    async getPredictions(gameweek) {
        return this._fetch(`/predictions/${gameweek}`);
    },
    
    /**
     * Compute and cache predictions for a gameweek
     */
    async computePredictions(gameweek) {
        return this._fetch(`/predictions/${gameweek}/compute`, { method: 'POST' });
    },
    
    /**
     * Get a cached value
     */
    async getCache(key) {
        return this._fetch(`/cache/${encodeURIComponent(key)}`);
    },
    
    /**
     * Set a cached value
     */
    async setCache(key, value, ttlSeconds = null, gameweek = null) {
        const body = { value };
        if (ttlSeconds) body.ttl = ttlSeconds;
        if (gameweek) body.gameweek = gameweek;
        
        return this._fetch(`/cache/${encodeURIComponent(key)}`, {
            method: 'PUT',
            body: JSON.stringify(body)
        });
    },
    
    /**
     * Delete a cached value
     */
    async deleteCache(key) {
        return this._fetch(`/cache/${encodeURIComponent(key)}`, { method: 'DELETE' });
    },
    
    // =========================================================================
    // Utility Methods
    // =========================================================================
    
    /**
     * Check if a player is owned
     */
    async isPlayerOwned(playerId, gameweek = null) {
        const ownedIds = await this.getOwnedIds(gameweek);
        return ownedIds.has(playerId);
    },
    
    /**
     * Get position name from position ID
     */
    getPositionName(positionId) {
        const positions = { 1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD' };
        return positions[positionId] || 'UNK';
    },
    
    /**
     * Get position ID from position name
     */
    getPositionId(positionName) {
        const positions = { 'GK': 1, 'DEF': 2, 'MID': 3, 'FWD': 4 };
        return positions[positionName.toUpperCase()] || 3;
    }
};

// Export for use in modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = FPLDB;
}

// Make available globally
window.FPLDB = FPLDB;

console.log('[FPLDB] Database client loaded');
