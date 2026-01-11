/**
 * FPL Analyzer - H2H Module
 * 
 * Handles head-to-head comparisons between squads.
 */

const H2H = {
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
     * Populate entry and gameweek dropdowns
     */
    populateDropdowns() {
        const entry1 = document.getElementById('h2hEntry1');
        const entry2 = document.getElementById('h2hEntry2');
        const gwSelect = document.getElementById('h2hGwSelect');
        
        const entries = State.getEntries();
        
        // Populate entry dropdowns
        [entry1, entry2].forEach((select, idx) => {
            if (!select) return;
            select.innerHTML = '<option value="">Select squad...</option>';
            entries.forEach(entry => {
                const option = document.createElement('option');
                option.value = entry.entry_id;
                option.textContent = entry.entry_name || `Entry ${entry.entry_id}`;
                select.appendChild(option);
            });
            
            // Default selections
            if (entries.length > idx) {
                select.value = entries[idx].entry_id;
            }
        });
        
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
        
        this.toggleDataWarning(!State.isInitialized());
    },
    
    /**
     * Show/hide data warning
     */
    toggleDataWarning(show) {
        const warning = document.getElementById('h2hRequiresData');
        if (warning) {
            warning.style.display = show ? 'block' : 'none';
        }
    },
    
    // ==========================================================================
    // H2H Comparison
    // ==========================================================================
    
    /**
     * Compare two squads
     */
    async compare() {
        const entry1 = document.getElementById('h2hEntry1')?.value;
        const entry2 = document.getElementById('h2hEntry2')?.value;
        const gameweek = document.getElementById('h2hGwSelect')?.value;
        const container = document.getElementById('h2hResult');
        
        if (!entry1 || !entry2) {
            if (container) {
                container.innerHTML = '<div class="alert warning">Select both squads to compare</div>';
            }
            return;
        }
        
        if (entry1 === entry2) {
            if (container) {
                container.innerHTML = '<div class="alert warning">Please select two different squads</div>';
            }
            return;
        }
        
        try {
            if (container) {
                container.innerHTML = '<div class="loading">Calculating predictions</div>';
            }
            
            const data = await FPL.getH2H(entry1, entry2, gameweek);
            
            if (container) {
                container.innerHTML = this.renderH2HResult(data);
            }
        } catch (error) {
            if (container) {
                container.innerHTML = `<div class="alert error">Comparison failed: ${error.message}</div>`;
            }
        }
    },
    
    /**
     * Render H2H comparison result
     */
    renderH2HResult(data) {
        const { team1, team2, differential, favorite, gameweek } = data;
        
        return `
            <div class="h2h-matchup-card">
                <div class="h2h-teams">
                    <div class="h2h-team">
                        <div class="h2h-team-name">${team1.name}</div>
                        <div class="h2h-team-points">${team1.expected_points.toFixed(1)}</div>
                        <div style="color: var(--text-secondary); font-size: 0.85rem;">
                            ${team1.formation}
                        </div>
                    </div>
                    <div class="h2h-vs">
                        <div style="font-size: 1.5rem; margin-bottom: 0.5rem;">⚔️</div>
                        <div>GW ${gameweek}</div>
                    </div>
                    <div class="h2h-team">
                        <div class="h2h-team-name">${team2.name}</div>
                        <div class="h2h-team-points">${team2.expected_points.toFixed(1)}</div>
                        <div style="color: var(--text-secondary); font-size: 0.85rem;">
                            ${team2.formation}
                        </div>
                    </div>
                </div>
                
                <div class="win-probability-bar">
                    <div class="win-prob-segment team1" style="width: ${team1.win_probability}%">
                        ${team1.win_probability > 15 ? team1.win_probability.toFixed(0) + '%' : ''}
                    </div>
                    <div class="win-prob-segment team2" style="width: ${team2.win_probability}%">
                        ${team2.win_probability > 15 ? team2.win_probability.toFixed(0) + '%' : ''}
                    </div>
                </div>
                
                <div style="text-align: center; margin: 1rem 0;">
                    <span class="badge ${team1.win_probability > team2.win_probability ? 'info' : 'success'}">
                        Favorite: ${favorite} (+${differential.toFixed(1)} pts)
                    </span>
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                ${this.renderTeamLineup(team1)}
                ${this.renderTeamLineup(team2)}
            </div>
        `;
    },
    
    /**
     * Render a team's optimal lineup
     */
    renderTeamLineup(team) {
        const players = team.optimal_11 || [];
        
        return `
            <div class="prediction-card">
                <h4 style="margin-bottom: 1rem;">${team.name}</h4>
                <table class="player-breakdown-table">
                    <thead>
                        <tr>
                            <th>Player</th>
                            <th>Opp</th>
                            <th style="text-align: right;">xPts</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${players.map(p => `
                            <tr>
                                <td>
                                    <span class="position-badge ${this.getPositionClass(p.position)}" style="margin-right: 0.5rem;">
                                        ${p.position_name || '?'}
                                    </span>
                                    ${p.player_name}
                                </td>
                                <td class="stat-cell">${p.opponent_name || '?'}</td>
                                <td class="stat-cell highlight">${p.expected_points.toFixed(1)}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                    <tfoot>
                        <tr style="font-weight: 700;">
                            <td colspan="2">Total</td>
                            <td class="stat-cell highlight">${team.expected_points.toFixed(1)}</td>
                        </tr>
                    </tfoot>
                </table>
            </div>
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
    }
};

// Make globally available
window.H2H = H2H;


