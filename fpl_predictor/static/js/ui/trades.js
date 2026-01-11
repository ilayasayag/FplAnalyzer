/**
 * FPL Analyzer - Trades Module
 * 
 * Handles trade suggestions and recommendations.
 */

const Trades = {
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
     * Populate entry dropdown
     */
    populateDropdowns() {
        const entrySelect = document.getElementById('tradeEntrySelect');
        
        if (entrySelect) {
            const entries = State.getEntries();
            entrySelect.innerHTML = '<option value="">Select your squad...</option>';
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
        const warning = document.getElementById('tradesRequiresData');
        if (warning) {
            warning.style.display = show ? 'block' : 'none';
        }
    },
    
    // ==========================================================================
    // Trade Suggestions
    // ==========================================================================
    
    /**
     * Get trade suggestions for selected squad
     */
    async getSuggestions() {
        const entrySelect = document.getElementById('tradeEntrySelect');
        const container = document.getElementById('tradeSuggestionsResult');
        
        const entryId = parseInt(entrySelect?.value);
        
        if (!entryId) {
            if (container) {
                container.innerHTML = '<div class="alert warning">Select your squad first</div>';
            }
            return;
        }
        
        try {
            if (container) {
                container.innerHTML = '<div class="loading">Analyzing trades</div>';
            }
            
            const data = await FPL.getTradeSuggestions(entryId);
            
            if (container) {
                container.innerHTML = this.renderSuggestions(data);
            }
        } catch (error) {
            if (container) {
                container.innerHTML = `<div class="alert error">Failed to get suggestions: ${error.message}</div>`;
            }
        }
    },
    
    /**
     * Render trade suggestions
     */
    renderSuggestions(data) {
        const { entry_name, target_teams, underperformers, squad_teams, current_gw } = data;
        
        return `
            <div style="margin-bottom: 2rem;">
                <h3 style="margin-bottom: 0.5rem;">${entry_name}</h3>
                <p style="color: var(--text-secondary);">
                    Suggestions based on GW${current_gw}+ fixtures
                </p>
            </div>
            
            ${this.renderTargetTeams(target_teams)}
            ${this.renderUnderperformers(underperformers)}
            ${this.renderCurrentTeams(squad_teams)}
        `;
    },
    
    /**
     * Render target teams with good fixtures
     */
    renderTargetTeams(targets) {
        if (!targets || targets.length === 0) {
            return `
                <div class="section" style="padding: 1rem;">
                    <h4 class="section-title">Target Teams</h4>
                    <div class="alert info">No obvious targets found. Your squad already has good fixture coverage.</div>
                </div>
            `;
        }
        
        const cards = targets.map(t => `
            <div class="card">
                <div class="card-header">
                    <h4 class="card-title">${t.team}</h4>
                    <span class="badge success">${t.reason}</span>
                </div>
                <h5 style="margin: 0.5rem 0; color: var(--text-secondary);">Top Players</h5>
                <div>
                    ${t.players.map(p => `
                        <div class="player-card-mini high-conf">
                            <span class="position-badge ${p.position.toLowerCase()}">${p.position}</span>
                            ${p.name}
                            <span style="color: var(--accent-emerald); font-weight: 600;">${p.ppg} PPG</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `).join('');
        
        return `
            <div class="section" style="padding: 1rem;">
                <h4 class="section-title">🎯 Target Teams</h4>
                <p style="color: var(--text-secondary); margin-bottom: 1rem;">
                    Teams with good upcoming fixtures that you don't have covered
                </p>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem;">
                    ${cards}
                </div>
            </div>
        `;
    },
    
    /**
     * Render underperforming players
     */
    renderUnderperformers(players) {
        if (!players || players.length === 0) {
            return `
                <div class="section" style="padding: 1rem; margin-top: 1rem;">
                    <h4 class="section-title">📉 Underperformers</h4>
                    <div class="alert success">No significant underperformers in your squad!</div>
                </div>
            `;
        }
        
        const rows = players.map(p => `
            <tr>
                <td>
                    <span class="position-badge ${p.position.toLowerCase()}">${p.position}</span>
                </td>
                <td>${p.name}</td>
                <td class="stat-cell">${p.team}</td>
                <td class="stat-cell negative">${p.ppg} PPG</td>
                <td style="color: var(--text-muted); font-size: 0.8rem;">${p.reason}</td>
            </tr>
        `).join('');
        
        return `
            <div class="section" style="padding: 1rem; margin-top: 1rem;">
                <h4 class="section-title">📉 Underperformers</h4>
                <p style="color: var(--text-secondary); margin-bottom: 1rem;">
                    Players who might be worth trading out
                </p>
                <table class="player-breakdown-table">
                    <thead>
                        <tr>
                            <th>Pos</th>
                            <th>Player</th>
                            <th>Team</th>
                            <th>PPG</th>
                            <th>Reason</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        `;
    },
    
    /**
     * Render current squad teams
     */
    renderCurrentTeams(teams) {
        if (!teams || teams.length === 0) {
            return '';
        }
        
        return `
            <div class="section" style="padding: 1rem; margin-top: 1rem;">
                <h4 class="section-title">📋 Your Team Coverage</h4>
                <div style="display: flex; flex-wrap: wrap; gap: 0.5rem;">
                    ${teams.map(t => `
                        <span class="badge info">${t}</span>
                    `).join('')}
                </div>
            </div>
        `;
    }
};

// Make globally available
window.Trades = Trades;


