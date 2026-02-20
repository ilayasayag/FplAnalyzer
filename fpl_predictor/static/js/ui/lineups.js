/**
 * Predicted Lineups UI Module
 * 
 * Displays predicted starting lineups with probabilities and injury status
 */

const Lineups = {
    currentGameweek: null,
    lineupsData: null,
    teamsData: {},
    
    /**
     * Initialize the lineups tab
     */
    init() {
        this.populateGameweekSelect();
    },
    
    /**
     * Populate the gameweek dropdown
     */
    populateGameweekSelect() {
        const select = document.getElementById('lineupsGwSelect');
        if (!select) return;
        
        select.innerHTML = '';
        
        // Get current GW from state or default to next GW
        const currentGW = State.currentEvent || 21;
        
        // Create options for next 5 gameweeks
        for (let gw = currentGW; gw <= Math.min(currentGW + 4, 38); gw++) {
            const option = document.createElement('option');
            option.value = gw;
            option.textContent = `GW${gw}${gw === currentGW ? ' (Next)' : ''}`;
            if (gw === currentGW) {
                option.selected = true;
            }
            select.appendChild(option);
        }
        
        this.currentGameweek = currentGW;
    },
    
    /**
     * Load predicted lineups for selected gameweek
     */
    async loadPredictions() {
        const select = document.getElementById('lineupsGwSelect');
        const gameweek = parseInt(select.value);
        
        if (!gameweek) {
            this.showStatus('Please select a gameweek', 'warning');
            return;
        }
        
        this.currentGameweek = gameweek;
        this.showStatus(`Loading predictions for GW${gameweek}...`, 'info');
        
        try {
            // Fetch lineup predictions from API
            const response = await fetch(`/api/predicted-lineups/${gameweek}`);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (!data.predictions || data.predictions.length === 0) {
                this.showStatus(
                    `No predictions available for GW${gameweek}. Click "Refresh Data" to fetch latest lineups.`, 
                    'warning'
                );
                this.renderEmpty();
                return;
            }
            
            this.lineupsData = data.predictions;
            this.showStatus(
                `Loaded ${data.predictions.length} player predictions for GW${gameweek}` +
                (data.last_updated ? ` (Updated: ${new Date(data.last_updated).toLocaleString()})` : ''),
                'success'
            );
            
            this.renderLineups();
            
        } catch (error) {
            console.error('Error loading lineup predictions:', error);
            this.showStatus(`Error loading predictions: ${error.message}`, 'error');
            this.renderEmpty();
        }
    },
    
    /**
     * Refresh predictions from source (triggers scraping)
     */
    async refreshPredictions() {
        const select = document.getElementById('lineupsGwSelect');
        const gameweek = parseInt(select.value);
        
        if (!gameweek) {
            this.showStatus('Please select a gameweek', 'warning');
            return;
        }
        
        this.showStatus(`Refreshing predictions for GW${gameweek}... This may take 30-60 seconds.`, 'info');
        
        try {
            const response = await fetch(`/api/predicted-lineups/refresh/${gameweek}`, {
                method: 'POST'
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            this.showStatus(
                `Refreshed ${data.predictions_count} predictions for GW${gameweek}`,
                'success'
            );
            
            // Reload predictions to show updated data
            await this.loadPredictions();
            
        } catch (error) {
            console.error('Error refreshing predictions:', error);
            this.showStatus(`Error refreshing: ${error.message}`, 'error');
        }
    },
    
    /**
     * Render lineup predictions grouped by team
     */
    renderLineups() {
        const grid = document.getElementById('lineupsGrid');
        if (!grid || !this.lineupsData) return;
        
        // Group predictions by team
        const teamGroups = {};
        this.lineupsData.forEach(pred => {
            const teamId = pred.team_id;
            if (!teamGroups[teamId]) {
                teamGroups[teamId] = [];
            }
            teamGroups[teamId].push(pred);
        });
        
        // Sort teams by ID
        const sortedTeams = Object.keys(teamGroups).sort((a, b) => parseInt(a) - parseInt(b));
        
        // Render team cards
        grid.innerHTML = sortedTeams.map(teamId => {
            const players = teamGroups[teamId];
            return this.renderTeamCard(teamId, players);
        }).join('');
    },
    
    /**
     * Render a single team card
     */
    renderTeamCard(teamId, players) {
        // Get team name from state
        const team = State.teams?.find(t => t.id === parseInt(teamId));
        const teamName = team ? team.name : `Team ${teamId}`;
        const teamCode = team ? team.short_name : 'TBD';
        
        // Sort players by start probability (highest first)
        players.sort((a, b) => b.start_probability - a.start_probability);
        
        // Categorize players
        const starters = players.filter(p => p.start_probability >= 0.7 && !p.injured && !p.suspended);
        const doubtful = players.filter(p => 
            (p.start_probability >= 0.3 && p.start_probability < 0.7) || p.doubtful
        );
        const out = players.filter(p => p.injured || p.suspended || p.start_probability < 0.3);
        
        return `
            <div class="lineup-team-card">
                <div class="lineup-team-header">
                    <div class="lineup-team-name">
                        <span class="team-badge">${teamCode}</span>
                        <span>${teamName}</span>
                    </div>
                    <div class="lineup-team-stats">
                        <span class="stat-badge success">${starters.length} Starting</span>
                        ${doubtful.length > 0 ? `<span class="stat-badge warning">${doubtful.length} Doubtful</span>` : ''}
                        ${out.length > 0 ? `<span class="stat-badge danger">${out.length} Out</span>` : ''}
                    </div>
                </div>
                
                <div class="lineup-players">
                    ${starters.length > 0 ? `
                        <div class="lineup-section">
                            <div class="lineup-section-title">✅ Expected Starters</div>
                            ${starters.map(p => this.renderPlayerRow(p)).join('')}
                        </div>
                    ` : ''}
                    
                    ${doubtful.length > 0 ? `
                        <div class="lineup-section">
                            <div class="lineup-section-title">⚠️ Doubtful</div>
                            ${doubtful.map(p => this.renderPlayerRow(p)).join('')}
                        </div>
                    ` : ''}
                    
                    ${out.length > 0 ? `
                        <div class="lineup-section">
                            <div class="lineup-section-title">❌ Unlikely / Injured</div>
                            ${out.map(p => this.renderPlayerRow(p)).join('')}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    },
    
    /**
     * Render a single player row
     */
    renderPlayerRow(player) {
        const probability = Math.round(player.start_probability * 100);
        const statusBadge = this.getStatusBadge(player);
        const probabilityClass = this.getProbabilityClass(probability);
        
        // Get player details from state if available
        const playerDetails = State.allPlayers?.find(p => p.id === player.player_id);
        const playerName = playerDetails ? playerDetails.web_name : `Player ${player.player_id}`;
        
        return `
            <div class="lineup-player-row">
                <div class="player-info">
                    <span class="player-name" onclick="Lineups.showPlayerDetails(${player.player_id}, ${this.currentGameweek})">
                        ${playerName}
                    </span>
                    ${statusBadge}
                </div>
                <div class="player-probability">
                    <div class="probability-bar ${probabilityClass}">
                        <div class="probability-fill" style="width: ${probability}%"></div>
                    </div>
                    <span class="probability-text">${probability}%</span>
                </div>
            </div>
        `;
    },
    
    /**
     * Get status badge HTML
     */
    getStatusBadge(player) {
        if (player.injured) {
            return `<span class="status-badge injured" title="${player.injury_details || 'Injured'}">🔴 Injured</span>`;
        }
        if (player.suspended) {
            return `<span class="status-badge suspended" title="Suspended">🔴 Suspended</span>`;
        }
        if (player.doubtful) {
            return `<span class="status-badge doubtful" title="${player.injury_details || 'Doubtful'}">🟡 Doubtful</span>`;
        }
        return '';
    },
    
    /**
     * Get probability class for color coding
     */
    getProbabilityClass(probability) {
        if (probability >= 80) return 'prob-high';
        if (probability >= 50) return 'prob-medium';
        if (probability >= 30) return 'prob-low';
        return 'prob-very-low';
    },
    
    /**
     * Show player details modal (placeholder for future enhancement)
     */
    showPlayerDetails(playerId, gameweek) {
        console.log(`Show details for player ${playerId} in GW${gameweek}`);
        // TODO: Implement player detail modal with:
        // - Recent form
        // - Injury history
        // - Fixture difficulty
        // - Lineup probability trend
    },
    
    /**
     * Render empty state
     */
    renderEmpty() {
        const grid = document.getElementById('lineupsGrid');
        if (!grid) return;
        
        grid.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📋</div>
                <div class="empty-state-title">No lineup predictions available</div>
                <div class="empty-state-description">
                    Click "Refresh Data" to fetch the latest predicted lineups
                </div>
            </div>
        `;
    },
    
    /**
     * Show status message
     */
    showStatus(message, type = 'info') {
        const statusDiv = document.getElementById('lineupsStatus');
        if (!statusDiv) return;
        
        const alertClass = {
            'info': 'alert info',
            'success': 'alert success',
            'warning': 'alert warning',
            'error': 'alert error'
        }[type] || 'alert info';
        
        statusDiv.innerHTML = `<div class="${alertClass}">${message}</div>`;
        
        // Auto-hide success messages after 5 seconds
        if (type === 'success') {
            setTimeout(() => {
                statusDiv.innerHTML = '';
            }, 5000);
        }
    }
};

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => Lineups.init());
} else {
    Lineups.init();
}
