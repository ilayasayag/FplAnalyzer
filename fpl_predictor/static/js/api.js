/**
 * FPL Analyzer - API Client
 * 
 * Central interface for all backend API calls.
 * All modules use this for data fetching.
 */

const FPL = {
    // API base URL (same origin)
    baseUrl: '/api',
    
    // Cache for expensive requests
    _cache: {},
    
    // ==========================================================================
    // Core Methods
    // ==========================================================================
    
    /**
     * Make an API request
     * @param {string} endpoint - API endpoint
     * @param {Object} options - Fetch options
     * @returns {Promise<Object>} Response JSON
     */
    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        
        try {
            const response = await fetch(url, {
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                ...options
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.message || `API error: ${response.status}`);
            }
            
            return data;
        } catch (error) {
            console.error(`API Error [${endpoint}]:`, error);
            throw error;
        }
    },
    
    /**
     * GET request helper
     */
    async get(endpoint, params = {}) {
        const queryString = new URLSearchParams(params).toString();
        const url = queryString ? `${endpoint}?${queryString}` : endpoint;
        return this.request(url);
    },
    
    /**
     * POST request helper
     */
    async post(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    },
    
    // ==========================================================================
    // Health & Status
    // ==========================================================================
    
    /**
     * Check API health and initialization status
     */
    async health() {
        return this.get('/health');
    },
    
    /**
     * Check if data is loaded
     */
    async isInitialized() {
        const status = await this.health();
        return status.initialized;
    },
    
    // ==========================================================================
    // Data Import
    // ==========================================================================
    
    /**
     * Import FPL data from bookmarklet JSON
     * @param {Object} jsonData - Complete bookmarklet export
     */
    async importData(jsonData = null) {
        // If no data passed, get from textarea
        if (!jsonData) {
            const textarea = document.getElementById('jsonInput');
            const jsonText = textarea?.value?.trim();
            
            if (!jsonText) {
                this.showAlert('importResult', 'Please paste JSON data first', 'warning');
                return null;
            }
            
            try {
                jsonData = JSON.parse(jsonText);
            } catch (e) {
                this.showAlert('importResult', `Invalid JSON: ${e.message}`, 'error');
                return null;
            }
        }
        
        try {
            this.showAlert('importResult', 'Importing data...', 'info');
            
            // Send the data directly to the import endpoint
            // The API expects the full bookmarklet JSON object
            const result = await this.post('/import', jsonData);
            
            // Update state if State module is available
            if (typeof State !== 'undefined') {
                State.setInitialized(true);
                State.setStatistics(result.statistics);
            }
            
            // Refresh league data
            await this.refreshLeagueInfo();
            
            this.showAlert('importResult', 
                `✅ Imported ${result.statistics?.total_players || 0} players, ${result.statistics?.total_teams || 0} teams. ` +
                `Current GW: ${result.statistics?.current_gameweek || '?'}`, 
                'success'
            );
            
            // Update header status
            this.updateDataStatus(result.statistics);
            
            return result;
        } catch (error) {
            console.error('Import error:', error);
            this.showAlert('importResult', `Import failed: ${error.message}`, 'error');
            return null;
        }
    },
    
    /**
     * Load from file path (for development)
     */
    async loadFromFile(filePath) {
        return this.post('/load', { file_path: filePath });
    },
    
    /**
     * Load sample/demo data
     */
    async loadSampleData() {
        this.showAlert('importResult', 'Sample data loading not implemented yet. Please use the bookmarklet to fetch real data.', 'info');
    },
    
    // ==========================================================================
    // Fixtures
    // ==========================================================================
    
    /**
     * Get fixture difficulty grid
     * @param {number} gwStart - Start gameweek
     * @param {number} gwEnd - End gameweek
     */
    async getFixtureGrid(gwStart = 21, gwEnd = 38) {
        return this.get('/fixtures/grid', { gw_start: gwStart, gw_end: gwEnd });
    },
    
    /**
     * Get rotation/overlap analysis
     * @param {string} team1 - First team name
     * @param {string} team2 - Second team name (optional)
     */
    async getOverlap(team1, team2 = null) {
        const params = { team1 };
        if (team2) params.team2 = team2;
        return this.get('/fixtures/overlap', params);
    },
    
    // ==========================================================================
    // Predictions
    // ==========================================================================
    
    /**
     * Get prediction for a single player
     * @param {number} playerId - Player ID
     * @param {number} opponentId - Opponent team ID
     * @param {number} gameweek - Gameweek number
     * @param {boolean} isHome - Home or away
     */
    async predictPlayer(playerId, opponentId, gameweek, isHome = true) {
        return this.get(`/predict/player/${playerId}`, {
            opponent_id: opponentId,
            gameweek,
            is_home: isHome
        });
    },
    
    /**
     * Get predictions for an entire squad
     * @param {number} entryId - Squad entry ID
     * @param {number} gameweek - Gameweek number
     */
    async predictSquad(entryId, gameweek = null) {
        const params = {};
        if (gameweek) params.gameweek = gameweek;
        return this.get(`/predict/squad/${entryId}`, params);
    },
    
    // ==========================================================================
    // Squad Analysis
    // ==========================================================================
    
    /**
     * Get squad coverage analysis
     * @param {number} entryId - Squad entry ID
     */
    async getSquadAnalysis(entryId) {
        return this.get(`/squad/analysis/${entryId}`);
    },
    
    // ==========================================================================
    // Head-to-Head
    // ==========================================================================
    
    /**
     * Get H2H prediction between two squads
     * @param {number} entry1 - First squad entry ID
     * @param {number} entry2 - Second squad entry ID
     * @param {number} gameweek - Gameweek number
     */
    async getH2H(entry1, entry2, gameweek = null) {
        let endpoint = `/h2h/${entry1}/${entry2}`;
        const params = {};
        if (gameweek) params.gameweek = gameweek;
        return this.get(endpoint, params);
    },
    
    // ==========================================================================
    // Trades
    // ==========================================================================
    
    /**
     * Get trade suggestions for a squad
     * @param {number} entryId - Squad entry ID
     */
    async getTradeSuggestions(entryId) {
        return this.get(`/trades/suggestions/${entryId}`);
    },
    
    // ==========================================================================
    // Players & Teams
    // ==========================================================================
    
    /**
     * Search/list players
     * @param {Object} params - Search parameters
     */
    async getPlayers(params = {}) {
        return this.get('/players', params);
    },
    
    /**
     * Get single player details
     * @param {number} playerId - Player ID
     */
    async getPlayer(playerId) {
        return this.get(`/players/${playerId}`);
    },
    
    /**
     * List all teams
     */
    async getTeams() {
        return this.get('/teams');
    },
    
    /**
     * Get team details
     * @param {number} teamId - Team ID
     */
    async getTeam(teamId) {
        return this.get(`/teams/${teamId}`);
    },
    
    /**
     * Get batch summary
     */
    async getBatches() {
        return this.get('/batches');
    },
    
    // ==========================================================================
    // League
    // ==========================================================================
    
    /**
     * Get league information
     */
    async getLeagueInfo() {
        return this.get('/league');
    },
    
    /**
     * Refresh league info and update state
     */
    async refreshLeagueInfo() {
        try {
            const info = await this.getLeagueInfo();
            State.setLeagueInfo(info);
            return info;
        } catch (error) {
            console.warn('Could not refresh league info:', error.message);
            return null;
        }
    },
    
    // ==========================================================================
    // Export
    // ==========================================================================
    
    /**
     * Export predictions for all squads
     * @param {number} gameweek - Gameweek number
     */
    async exportPredictions(gameweek = null) {
        const params = {};
        if (gameweek) params.gameweek = gameweek;
        return this.post('/export/predictions', params);
    },
    
    // ==========================================================================
    // Bookmarklet
    // ==========================================================================
    
    /**
     * Generate bookmarklet code
     */
    generateBookmarklet() {
        const leagueIdInput = document.getElementById('leagueIdInput');
        const leagueId = leagueIdInput?.value?.trim();
        
        if (!leagueId) {
            alert('Please enter a League ID');
            return;
        }
        
        // Bookmarklet code - fetches all data from FPL Draft API
        const bookmarkletCode = `javascript:(function(){
            const LEAGUE_ID = ${leagueId};
            const BASE = 'https://draft.premierleague.com/api';
            let data = { league: null, bootstrap: null, playerDetails: {}, fetchedAt: new Date().toISOString() };
            
            async function fetchAll() {
                try {
                    console.log('Fetching league data...');
                    const [league, elements, bootstrap] = await Promise.all([
                        fetch(BASE + '/league/' + LEAGUE_ID + '/details').then(r => r.json()),
                        fetch(BASE + '/league/' + LEAGUE_ID + '/element-status').then(r => r.json()),
                        fetch(BASE + '/bootstrap-static').then(r => r.json())
                    ]);
                    
                    data.league = league;
                    data.elements = elements;
                    data.bootstrap = bootstrap;
                    
                    const playerIds = new Set();
                    Object.values(league.squads || {}).forEach(s => 
                        (s.picks || []).forEach(p => playerIds.add(p.element))
                    );
                    
                    console.log('Fetching ' + playerIds.size + ' player histories...');
                    const chunks = [];
                    const ids = Array.from(playerIds);
                    for (let i = 0; i < ids.length; i += 10) {
                        chunks.push(ids.slice(i, i + 10));
                    }
                    
                    for (const chunk of chunks) {
                        const results = await Promise.all(
                            chunk.map(id => fetch(BASE + '/element-summary/' + id).then(r => r.json()).catch(() => null))
                        );
                        chunk.forEach((id, i) => { if (results[i]) data.playerDetails[id] = results[i]; });
                    }
                    
                    console.log('Done! Copying to clipboard...');
                    const json = JSON.stringify(data);
                    navigator.clipboard.writeText(json).then(() => {
                        alert('FPL data copied to clipboard! Paste it into the analyzer.');
                    });
                } catch (e) {
                    alert('Error: ' + e.message);
                    console.error(e);
                }
            }
            fetchAll();
        })();`;
        
        // Show bookmarklet
        const area = document.getElementById('bookmarkletArea');
        const link = document.getElementById('bookmarkletLink');
        
        if (area && link) {
            link.href = bookmarkletCode;
            area.style.display = 'block';
        }
    },
    
    // ==========================================================================
    // UI Helpers
    // ==========================================================================
    
    /**
     * Show alert in a container
     */
    showAlert(containerId, message, type = 'info') {
        const container = document.getElementById(containerId);
        if (!container) return;
        
        container.innerHTML = `<div class="alert ${type}">${message}</div>`;
        container.style.display = 'block';
    },
    
    /**
     * Update the data status banner in header
     */
    updateDataStatus(stats) {
        const statusDiv = document.getElementById('dataStatus');
        if (!statusDiv) return;
        
        if (stats) {
            statusDiv.innerHTML = `
                ✅ Data loaded: ${stats.total_players} players, ${stats.total_teams} teams | 
                GW ${stats.current_gameweek} | 
                ${stats.league_entries || 0} league entries
            `;
            statusDiv.className = 'alert success';
            statusDiv.style.display = 'block';
        } else {
            statusDiv.innerHTML = '⚠️ No data loaded. Import your league data to get started.';
            statusDiv.className = 'alert warning';
            statusDiv.style.display = 'block';
        }
    }
};

// Make globally available
window.FPL = FPL;

