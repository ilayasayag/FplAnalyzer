/**
 * FPL Analyzer - Predictions Module
 * 
 * Handles GW predictions and team rankings.
 */

const Predictions = {
    // ==========================================================================
    // Initialization
    // ==========================================================================
    
    init() {
        this.populateDropdowns();
        
        // Subscribe to state changes
        State.subscribe('entries', () => this.populateDropdowns());
        State.subscribe('initialized', (init) => this.toggleDataWarning(!init));
    },
    
    /**
     * Populate gameweek and entry dropdowns
     */
    populateDropdowns() {
        const gwSelect = document.getElementById('predGwSelect');
        const entrySelect = document.getElementById('predEntrySelect');
        
        // Populate GW dropdown
        if (gwSelect) {
            const currentGw = State.getCurrentGameweek();
            gwSelect.innerHTML = '';
            for (let gw = Math.max(1, currentGw - 5); gw <= 38; gw++) {
                const option = document.createElement('option');
                option.value = gw;
                option.textContent = `GW ${gw}`;
                if (gw === currentGw) option.selected = true;
                gwSelect.appendChild(option);
            }
        }
        
        // Populate entry dropdown
        if (entrySelect) {
            const entries = State.getEntries();
            entrySelect.innerHTML = '<option value="">Select squad...</option>';
            entries.forEach(entry => {
                const option = document.createElement('option');
                option.value = entry.entry_id;
                option.textContent = entry.entry_name || `Entry ${entry.entry_id}`;
                entrySelect.appendChild(option);
            });
        }
        
        this.toggleDataWarning(!State.isInitialized());
    },
    
    /**
     * Show/hide data warning
     */
    toggleDataWarning(show) {
        const warning = document.getElementById('predictionRequiresData');
        if (warning) {
            warning.style.display = show ? 'block' : 'none';
        }
    },
    
    // ==========================================================================
    // Squad Predictions
    // ==========================================================================
    
    /**
     * Load predictions for selected squad
     */
    async loadSquadPredictions() {
        const entrySelect = document.getElementById('predEntrySelect');
        const gwSelect = document.getElementById('predGwSelect');
        const container = document.getElementById('squadPredictionResult');
        
        const entryId = parseInt(entrySelect?.value);
        const gameweek = parseInt(gwSelect?.value);
        
        if (!entryId) {
            if (container) {
                container.innerHTML = '<div class="alert warning">Select a squad first</div>';
            }
            return;
        }
        
        try {
            if (container) {
                container.innerHTML = '<div class="loading">Loading predictions</div>';
            }
            
            const data = await FPL.predictSquad(entryId, gameweek);
            
            if (container) {
                container.innerHTML = this.renderSquadPrediction(data);
            }
        } catch (error) {
            if (container) {
                container.innerHTML = `<div class="alert error">Failed to load predictions: ${error.message}</div>`;
            }
        }
    },
    
    /**
     * Render squad prediction result
     */
    renderSquadPrediction(data) {
        const { squad_name, gameweek, optimal_11, optimal_formation, total_expected_points, predictions } = data;
        
        // Sort players: starters first (by position), then bench
        const starters = optimal_11 || [];
        const starterIds = new Set(starters.map(p => p.player_id));
        const bench = (predictions || []).filter(p => !starterIds.has(p.player_id));
        
        return `
            <div class="prediction-card">
                <div class="card-header">
                    <h3 class="card-title">${squad_name}</h3>
                    <span class="badge info">GW ${gameweek}</span>
                </div>
                
                <div class="team-rank-bar">
                    <div class="points-bar">
                        <div class="points-bar-fill" style="width: ${Math.min(100, total_expected_points / 80 * 100)}%">
                            ${total_expected_points.toFixed(1)} pts
                        </div>
                    </div>
                </div>
                
                <div style="margin-bottom: 1rem;">
                    <span class="badge success">Formation: ${optimal_formation || 'Unknown'}</span>
                </div>
                
                <h4 style="margin: 1rem 0 0.5rem;">Starting XI</h4>
                ${this.renderPlayerTable(starters, true)}
                
                <h4 style="margin: 1.5rem 0 0.5rem; color: var(--text-secondary);">Bench</h4>
                ${this.renderPlayerTable(bench, false)}
            </div>
        `;
    },
    
    /**
     * Render player prediction table
     */
    renderPlayerTable(players, isStarters) {
        if (!players || players.length === 0) {
            return '<p style="color: var(--text-muted);">No players</p>';
        }
        
        const rows = players.map(p => {
            const posClass = this.getPositionClass(p.position);
            const confClass = p.confidence >= 0.7 ? 'high-conf' : (p.confidence >= 0.4 ? 'med-conf' : 'low-conf');
            const warnings = p.warnings && p.warnings.length > 0 ? 
                `<span title="${p.warnings.join(', ')}" style="color: var(--accent-amber);">⚠️</span>` : '';
            
            return `
                <tr class="${isStarters ? 'starter' : 'bench'}">
                    <td>
                        <span class="position-badge ${posClass}">${p.position_name || p.position}</span>
                    </td>
                    <td>${p.player_name}${warnings}</td>
                    <td class="stat-cell">${p.opponent_name || '???'}</td>
                    <td class="stat-cell ${p.is_home ? '' : ''}">${p.is_home ? 'H' : 'A'}</td>
                    <td class="stat-cell highlight">${p.expected_points.toFixed(1)}</td>
                    <td class="stat-cell">${(p.confidence * 100).toFixed(0)}%</td>
                </tr>
            `;
        }).join('');
        
        return `
            <table class="player-breakdown-table">
                <thead>
                    <tr>
                        <th>Pos</th>
                        <th>Player</th>
                        <th>Opp</th>
                        <th>V</th>
                        <th>xPts</th>
                        <th>Conf</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        `;
    },
    
    /**
     * Get position CSS class
     */
    getPositionClass(position) {
        const pos = typeof position === 'string' ? position.toLowerCase() : '';
        if (pos.includes('gk') || position === 1) return 'gk';
        if (pos.includes('def') || position === 2) return 'def';
        if (pos.includes('mid') || position === 3) return 'mid';
        if (pos.includes('fwd') || position === 4) return 'fwd';
        return '';
    },
    
    // ==========================================================================
    // Team Rankings
    // ==========================================================================
    
    /**
     * Load all team rankings for a gameweek
     */
    async loadRankings() {
        const container = document.getElementById('teamRankings');
        if (!container) return;
        
        const entries = State.getEntries();
        if (entries.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📊</div>
                    <div class="empty-state-title">No squads loaded</div>
                    <div class="empty-state-description">Import league data to see team rankings</div>
                </div>
            `;
            return;
        }
        
        try {
            container.innerHTML = '<div class="loading">Loading rankings</div>';
            
            const gameweek = State.getCurrentGameweek();
            const predictions = await Promise.all(
                entries.map(e => FPL.predictSquad(e.entry_id, gameweek).catch(() => null))
            );
            
            // Sort by expected points
            const ranked = predictions
                .filter(p => p !== null)
                .sort((a, b) => b.total_expected_points - a.total_expected_points);
            
            container.innerHTML = this.renderRankings(ranked);
        } catch (error) {
            container.innerHTML = `<div class="alert error">Failed to load rankings: ${error.message}</div>`;
        }
    },
    
    /**
     * Render team rankings grid
     */
    renderRankings(teams) {
        if (!teams || teams.length === 0) {
            return '<div class="empty-state"><div class="empty-state-title">No rankings available</div></div>';
        }
        
        const maxPts = Math.max(...teams.map(t => t.total_expected_points));
        
        return teams.map((team, idx) => {
            const rankClass = idx === 0 ? 'gold' : (idx === 1 ? 'silver' : (idx === 2 ? 'bronze' : 'default'));
            const widthPct = (team.total_expected_points / maxPts) * 100;
            const isWinner = idx === 0;
            
            return `
                <div class="prediction-card ${isWinner ? 'winner' : ''}">
                    <div class="team-rank-bar">
                        <div class="rank-badge ${rankClass}">${idx + 1}</div>
                        <div style="flex: 1;">
                            <div style="font-weight: 600; margin-bottom: 0.25rem;">${team.squad_name}</div>
                            <div class="points-bar">
                                <div class="points-bar-fill" style="width: ${widthPct}%">
                                    ${team.total_expected_points.toFixed(1)} pts
                                </div>
                            </div>
                        </div>
                    </div>
                    <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.5rem;">
                        Formation: ${team.optimal_formation || 'Unknown'}
                    </div>
                </div>
            `;
        }).join('');
    }
};

// Make globally available
window.Predictions = Predictions;

