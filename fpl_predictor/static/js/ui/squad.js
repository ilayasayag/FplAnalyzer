/**
 * FPL Analyzer - Squad Analysis Module
 * 
 * Handles squad coverage analysis and suggestions.
 */

const Squad = {
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
        const entrySelect = document.getElementById('squadEntrySelect');
        
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
        const warning = document.getElementById('squadRequiresData');
        if (warning) {
            warning.style.display = show ? 'block' : 'none';
        }
    },
    
    // ==========================================================================
    // Squad Analysis
    // ==========================================================================
    
    /**
     * Analyze the selected squad
     */
    async analyzeSquad() {
        const entrySelect = document.getElementById('squadEntrySelect');
        const container = document.getElementById('squadAnalysisResult');
        
        const entryId = parseInt(entrySelect?.value);
        
        if (!entryId) {
            if (container) {
                container.innerHTML = '<div class="alert warning">Select a squad first</div>';
            }
            return;
        }
        
        try {
            if (container) {
                container.innerHTML = '<div class="loading">Analyzing squad</div>';
            }
            
            const data = await FPL.getSquadAnalysis(entryId);
            
            if (container) {
                container.innerHTML = this.renderSquadAnalysis(data);
            }
        } catch (error) {
            if (container) {
                container.innerHTML = `<div class="alert error">Analysis failed: ${error.message}</div>`;
            }
        }
    },
    
    /**
     * Render squad analysis result
     */
    renderSquadAnalysis(data) {
        const { entry_name, squad, coverage, suggestions } = data;
        
        return `
            <div class="squad-builder">
                <div>
                    <h3 style="margin-bottom: 1rem;">${entry_name}</h3>
                    
                    ${this.renderPositionBreakdown(squad)}
                    ${this.renderCoverageHeatmap(coverage)}
                    ${this.renderSuggestions(suggestions)}
                </div>
                
                <div class="squad-summary">
                    <h4 style="margin-bottom: 1rem;">Summary</h4>
                    ${this.renderSummaryStats(data)}
                </div>
            </div>
        `;
    },
    
    /**
     * Render position breakdown
     */
    renderPositionBreakdown(squad) {
        const { by_position, team_counts } = squad;
        
        const positionSections = Object.entries(by_position).map(([pos, players]) => {
            const posClass = pos.toLowerCase();
            
            return `
                <div class="position-section">
                    <div class="position-title">
                        <span class="position-badge ${posClass}">${pos}</span>
                        <span>${players.length} players</span>
                    </div>
                    <div class="player-checkboxes">
                        ${players.map(p => `
                            <div class="player-checkbox selected">
                                ${p.name} <span style="color: var(--text-muted); font-size: 0.8rem;">(${p.team})</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        }).join('');
        
        return `
            <div class="section" style="padding: 1rem;">
                <h4 class="section-title">Squad Composition</h4>
                ${positionSections}
            </div>
        `;
    },
    
    /**
     * Render coverage heatmap
     */
    renderCoverageHeatmap(coverage) {
        const { by_gameweek, weak_gameweeks, total_weak } = coverage;
        
        // Create a simple heatmap row
        const cells = Object.entries(by_gameweek).map(([gw, data]) => {
            const isWeak = !data.has_11;
            const color = data.easy_count >= 11 ? 'var(--easy-game)' : 
                         (data.easy_count >= 8 ? 'var(--medium-game)' : 'var(--hard-game)');
            
            return `
                <td style="background: ${color}; text-align: center; padding: 0.5rem; border-radius: 4px;"
                    title="GW${gw}: ${data.easy_count} easy fixtures">
                    ${data.easy_count}
                </td>
            `;
        }).join('');
        
        const weaknessAlert = total_weak > 0 ? `
            <div class="alert warning" style="margin-top: 1rem;">
                ⚠️ ${total_weak} gameweek(s) with fewer than 11 easy fixtures: 
                <strong>GW ${weak_gameweeks.slice(0, 5).join(', ')}${weak_gameweeks.length > 5 ? '...' : ''}</strong>
            </div>
        ` : `
            <div class="alert success" style="margin-top: 1rem;">
                ✅ Good coverage! All gameweeks have 11+ easy fixtures.
            </div>
        `;
        
        return `
            <div class="section" style="padding: 1rem; margin-top: 1rem;">
                <h4 class="section-title">Fixture Coverage</h4>
                <div style="overflow-x: auto;">
                    <table class="fixture-heatmap-table" style="width: 100%;">
                        <thead>
                            <tr>
                                ${Object.keys(by_gameweek).map(gw => `<th>GW${gw}</th>`).join('')}
                            </tr>
                        </thead>
                        <tbody>
                            <tr>${cells}</tr>
                        </tbody>
                    </table>
                </div>
                ${weaknessAlert}
            </div>
        `;
    },
    
    /**
     * Render suggestions
     */
    renderSuggestions(suggestions) {
        if (!suggestions || suggestions.length === 0) {
            return `
                <div class="section" style="padding: 1rem; margin-top: 1rem;">
                    <h4 class="section-title">Suggestions</h4>
                    <div class="alert success">No issues found! Your squad looks balanced.</div>
                </div>
            `;
        }
        
        const items = suggestions.map(s => {
            const iconMap = {
                'weak_coverage': '📉',
                'team_concentration': '⚠️',
                'high': '🔴',
                'medium': '🟡',
                'low': '🟢'
            };
            
            const icon = iconMap[s.type] || iconMap[s.priority] || '💡';
            const priorityClass = s.priority === 'high' ? 'danger' : (s.priority === 'medium' ? 'warning' : 'info');
            
            return `
                <div class="alert ${priorityClass}">
                    ${icon} <strong>${s.type.replace('_', ' ').toUpperCase()}</strong>: ${s.message}
                </div>
            `;
        }).join('');
        
        return `
            <div class="section" style="padding: 1rem; margin-top: 1rem;">
                <h4 class="section-title">Suggestions</h4>
                ${items}
            </div>
        `;
    },
    
    /**
     * Render summary statistics
     */
    renderSummaryStats(data) {
        const { squad, coverage } = data;
        const teamCount = Object.keys(squad.team_counts).length;
        const maxTeam = Object.entries(squad.team_counts)
            .sort((a, b) => b[1] - a[1])[0];
        
        return `
            <div class="squad-counter">
                <div class="counter-item">
                    <div class="counter-value">${Object.values(squad.by_position).flat().length}</div>
                    <div class="counter-label">Players</div>
                </div>
                <div class="counter-item">
                    <div class="counter-value">${teamCount}</div>
                    <div class="counter-label">Teams</div>
                </div>
                <div class="counter-item">
                    <div class="counter-value ${coverage.total_weak > 3 ? 'bad' : 'good'}">${coverage.total_weak}</div>
                    <div class="counter-label">Weak GWs</div>
                </div>
                <div class="counter-item">
                    <div class="counter-value">${maxTeam ? maxTeam[1] : 0}</div>
                    <div class="counter-label">Max/Team</div>
                </div>
            </div>
            
            <h5 style="margin: 1rem 0 0.5rem; color: var(--text-secondary);">Team Distribution</h5>
            <div style="font-size: 0.85rem;">
                ${Object.entries(squad.team_counts)
                    .sort((a, b) => b[1] - a[1])
                    .map(([team, count]) => `
                        <div style="display: flex; justify-content: space-between; margin-bottom: 0.25rem;">
                            <span>${team}</span>
                            <span style="color: var(--text-muted);">${count}</span>
                        </div>
                    `).join('')}
            </div>
        `;
    }
};

// Make globally available
window.Squad = Squad;


