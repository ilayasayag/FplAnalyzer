/**
 * FPL Analyzer - Fixtures Module
 * 
 * Handles fixture grid display and rotation analysis.
 */

const Fixtures = {
    // Team name list (for dropdowns)
    teams: [],
    
    // ==========================================================================
    // Initialization
    // ==========================================================================
    
    async init() {
        await this.loadTeams();
        await this.loadGrid();
    },
    
    /**
     * Load team names for dropdowns
     */
    async loadTeams() {
        try {
            const data = await FPL.getFixtureGrid(20, 38);
            this.teams = data.teams.map(t => t.team);
            this.populateTeamDropdowns();
        } catch (error) {
            console.error('Failed to load teams:', error);
        }
    },
    
    /**
     * Populate team select dropdowns
     */
    populateTeamDropdowns() {
        const team1 = document.getElementById('team1Select');
        const team2 = document.getElementById('team2Select');
        
        if (!team1 || !team2) return;
        
        [team1, team2].forEach((select, idx) => {
            select.innerHTML = '<option value="">Select team...</option>';
            this.teams.forEach(team => {
                const option = document.createElement('option');
                option.value = team;
                option.textContent = team;
                select.appendChild(option);
            });
            
            // Default selection
            if (this.teams.length > idx) {
                select.value = this.teams[idx];
            }
        });
    },
    
    // ==========================================================================
    // Fixture Grid
    // ==========================================================================
    
    /**
     * Load and render the fixture grid
     */
    async loadGrid() {
        const container = document.getElementById('fixtureGrid');
        if (!container) return;
        
        const gwStart = parseInt(document.getElementById('gwStart')?.value) || 20;
        const gwEnd = parseInt(document.getElementById('gwEnd')?.value) || 38;
        
        try {
            container.innerHTML = '<div class="loading">Loading fixtures</div>';
            
            const data = await FPL.getFixtureGrid(gwStart, gwEnd);
            container.innerHTML = this.renderGrid(data);
        } catch (error) {
            container.innerHTML = `<div class="alert error">Failed to load fixtures: ${error.message}</div>`;
        }
    },
    
    /**
     * Render the fixture grid HTML
     */
    renderGrid(data) {
        const { gw_start, gw_end, teams } = data;
        
        // Build header row
        let headerCells = '<th>Team</th><th>Easy</th>';
        for (let gw = gw_start; gw <= gw_end; gw++) {
            headerCells += `<th>GW${gw}</th>`;
        }
        
        // Build team rows
        let rows = '';
        teams.forEach(team => {
            let cells = `
                <td class="team-name">${team.abbrev}</td>
                <td class="stat-cell">${team.easy_count}</td>
            `;
            
            team.gameweeks.forEach(gw => {
                const fdrClass = this.getFdrClass(gw.fdr);
                const venue = gw.is_home ? '' : '';  // Already in opponent string
                cells += `<td class="${fdrClass}" title="${team.team} vs ${gw.opponent}">${gw.opponent}</td>`;
            });
            
            rows += `<tr>${cells}</tr>`;
        });
        
        return `
            <table class="fixture-table">
                <thead><tr>${headerCells}</tr></thead>
                <tbody>${rows}</tbody>
            </table>
        `;
    },
    
    /**
     * Get CSS class for FDR value
     */
    getFdrClass(fdr) {
        if (fdr <= 2) return 'fdr-2';
        if (fdr === 3) return 'fdr-3';
        if (fdr === 4) return 'fdr-4';
        return 'fdr-5';
    },
    
    // ==========================================================================
    // Overlap Analysis
    // ==========================================================================
    
    /**
     * Analyze rotation between two teams
     */
    async analyzeOverlap() {
        const team1 = document.getElementById('team1Select')?.value;
        const team2 = document.getElementById('team2Select')?.value;
        const resultDiv = document.getElementById('overlapResult');
        const bestDiv = document.getElementById('bestOverlaps');
        
        if (!team1) {
            if (resultDiv) resultDiv.innerHTML = '<div class="alert warning">Select at least one team</div>';
            return;
        }
        
        try {
            if (team2 && team2 !== team1) {
                // Compare specific pair
                const data = await FPL.getOverlap(team1, team2);
                if (resultDiv) resultDiv.innerHTML = this.renderOverlapCard(data);
            }
            
            // Get best partners
            const partners = await FPL.getOverlap(team1);
            if (bestDiv) {
                bestDiv.innerHTML = this.renderBestPartners(partners);
            }
        } catch (error) {
            if (resultDiv) resultDiv.innerHTML = `<div class="alert error">Analysis failed: ${error.message}</div>`;
        }
    },
    
    /**
     * Render a single overlap analysis card
     */
    renderOverlapCard(data) {
        const coverageClass = data.coverage >= 15 ? 'good' : (data.coverage >= 10 ? 'neutral' : 'bad');
        const dupClass = data.duplications <= 3 ? 'good' : (data.duplications <= 6 ? 'neutral' : 'bad');
        const emptyClass = data.empty_weeks <= 3 ? 'good' : (data.empty_weeks <= 5 ? 'neutral' : 'bad');
        
        return `
            <div class="overlap-card" style="max-width: 400px;">
                <div class="team-pair">
                    ${data.team1} <span>+</span> ${data.team2}
                </div>
                <div class="overlap-stats">
                    <div class="stat-item">
                        <div class="stat-value ${coverageClass}">${data.coverage}</div>
                        <div class="stat-label">Coverage</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value ${dupClass}">${data.duplications}</div>
                        <div class="stat-label">Overlap</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value ${emptyClass}">${data.empty_weeks}</div>
                        <div class="stat-label">Empty</div>
                    </div>
                </div>
                <div style="margin-top: 1rem; font-size: 0.85rem; color: var(--text-secondary);">
                    Coverage: ${data.coverage_pct}% of gameweeks
                </div>
            </div>
        `;
    },
    
    /**
     * Render best rotation partners grid
     */
    renderBestPartners(data) {
        if (!data.best_partners || data.best_partners.length === 0) {
            return '<div class="empty-state"><div class="empty-state-title">No partners found</div></div>';
        }
        
        return data.best_partners.map((pair, idx) => {
            const isTop = idx < 3;
            const coverageClass = pair.coverage >= 15 ? 'good' : (pair.coverage >= 10 ? 'neutral' : 'bad');
            const dupClass = pair.duplications <= 3 ? 'good' : (pair.duplications <= 6 ? 'neutral' : 'bad');
            
            return `
                <div class="overlap-card ${isTop ? 'best' : ''}" style="${isTop ? 'border-color: var(--accent-emerald);' : ''}">
                    <div class="team-pair">
                        ${isTop ? `<span class="rank-badge ${idx === 0 ? 'gold' : idx === 1 ? 'silver' : 'bronze'}">${idx + 1}</span>` : ''}
                        ${pair.team1} <span>+</span> ${pair.team2}
                    </div>
                    <div class="overlap-stats">
                        <div class="stat-item">
                            <div class="stat-value ${coverageClass}">${pair.coverage}</div>
                            <div class="stat-label">Coverage</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value ${dupClass}">${pair.duplications}</div>
                            <div class="stat-label">Overlap</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value">${pair.coverage_pct}%</div>
                            <div class="stat-label">%</div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }
};

// Make globally available
window.Fixtures = Fixtures;

