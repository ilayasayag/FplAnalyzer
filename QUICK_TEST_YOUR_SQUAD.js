// ===================================================================
// 🚀 QUICK FPL SQUAD & TRADE INSPECTOR
// ===================================================================
// INSTRUCTIONS:
// 1. Go to draft.premierleague.com (make sure you're logged in)
// 2. Open Console (F12 or Cmd+Option+I)
// 3. Copy-paste this ENTIRE file
// 4. Press Enter
// 5. Wait 3-5 seconds for results
// 6. Copy the ENTIRE console output and share it
// ===================================================================

const LEAGUE_ID = 201560;
const CURRENT_GW = 22; // Change if needed

// Your two teams
const YOUR_TEAMS = {
  'Hapoel Eliyahu (IA)': 822133,
  'CHANGE NAME (IA1)': 830139
};

// Other teams in league
const OTHER_TEAMS = {
  'Johnny (Yoni)': 827066,
  'Roy': 822203,
  'Hapoel Yehuda (Ido)': 827275,
  'The Gunners (Yuval)': 829475,
  'Red Devils FC (Nadav)': 829535,
  'McShaike (Shai)': 830333
};

// Players to track (Saliba/Gabriel trade)
const TRACKED_PLAYERS = {
  6: 'Saliba',
  5: 'Gabriel'
};

console.clear();
console.log('═══════════════════════════════════════════════════════');
console.log('🔍 FPL SQUAD & TRADE INSPECTOR');
console.log('═══════════════════════════════════════════════════════\n');
console.log(`League: ${LEAGUE_ID}`);
console.log(`Checking: GW${CURRENT_GW}\n`);
console.log('⏳ Fetching data... please wait...\n');

// Store results
const results = {
  squads: {},
  transactions: null,
  trades: null
};

// Helper to fetch with error handling
async function fetchAPI(url, label) {
  try {
    const response = await fetch(url);
    console.log(`[${response.status}] ${label}`);
    if (response.ok) {
      return await response.json();
    }
    return null;
  } catch (e) {
    console.log(`[ERROR] ${label}: ${e.message}`);
    return null;
  }
}

// Main function
async function inspectFPL() {
  // 0. First, get league details to check waiver status
  console.log('═══ CHECKING LEAGUE STATUS ═══\n');
  
  const leagueDetails = await fetchAPI(
    `https://draft.premierleague.com/api/league/${LEAGUE_ID}/details`,
    'League Details'
  );
  
  if (leagueDetails) {
    const league = leagueDetails.league || {};
    const matches = leagueDetails.matches || [];
    
    console.log(`League: ${league.name || 'Unknown'}`);
    console.log(`Current Event: ${league.current_event || 'Unknown'}`);
    console.log(`Start Event: ${league.start_event || 'Unknown'}`);
    
    // Check current GW matches to see waiver status
    const currentGWMatches = matches.filter(m => m.event === CURRENT_GW);
    if (currentGWMatches.length > 0) {
      const sample = currentGWMatches[0];
      console.log(`\nGW${CURRENT_GW} Status:`);
      console.log(`  Finished: ${sample.finished || false}`);
      console.log(`  Started: ${sample.started || false}`);
      if (sample.league_entry_1_points !== null) {
        console.log(`  Points recorded: YES (GW is active/finished)`);
      }
    }
    
    // Try to get element status for waiver info
    const elementStatus = await fetchAPI(
      `https://draft.premierleague.com/api/draft/league/${LEAGUE_ID}/element-status`,
      'Element Status (ownership)'
    );
    
    if (elementStatus && elementStatus.element_status) {
      console.log(`\nOwnership data: ${elementStatus.element_status.length} players tracked`);
    }
    
    console.log('');
  }
  
  // 1. Fetch all squads
  console.log('═══ FETCHING SQUADS ═══\n');
  
  const allTeams = { ...YOUR_TEAMS, ...OTHER_TEAMS };
  
  for (const [name, entryId] of Object.entries(allTeams)) {
    const squad = await fetchAPI(
      `https://draft.premierleague.com/api/entry/${entryId}/event/${CURRENT_GW}`,
      `Squad: ${name} (${entryId})`
    );
    
    if (squad && squad.picks) {
      results.squads[entryId] = {
        name,
        picks: squad.picks,
        playerIds: squad.picks.map(p => p.element),
        entry_history: squad.entry_history || {}
      };
    }
  }
  
  results.leagueDetails = leagueDetails;
  
  // 2. Fetch transactions
  console.log('\n═══ FETCHING TRANSACTIONS ═══\n');
  
  results.transactions = await fetchAPI(
    `https://draft.premierleague.com/api/draft/league/${LEAGUE_ID}/transactions`,
    'Transactions'
  );
  
  // 3. Try trades endpoint
  console.log('\n═══ CHECKING TRADES ENDPOINT ═══\n');
  
  results.trades = await fetchAPI(
    `https://draft.premierleague.com/api/draft/league/${LEAGUE_ID}/trades`,
    'Trades'
  );
  
  // 4. Analyze results
  console.log('\n');
  console.log('═══════════════════════════════════════════════════════');
  console.log('📊 ANALYSIS RESULTS');
  console.log('═══════════════════════════════════════════════════════\n');
  
  // Check who has Saliba and Gabriel
  console.log('🔍 SALIBA/GABRIEL TRADE CHECK:\n');
  
  for (const [entryId, data] of Object.entries(results.squads)) {
    const hasSaliba = data.playerIds.includes(6);
    const hasGabriel = data.playerIds.includes(5);
    
    if (hasSaliba || hasGabriel) {
      console.log(`${data.name}:`);
      if (hasSaliba) console.log(`  ✅ Has Saliba (6)`);
      if (hasGabriel) console.log(`  ✅ Has Gabriel (5)`);
      console.log('');
    }
  }
  
  // Show your squads in detail
  console.log('\n═══ YOUR SQUADS (All Player IDs) ═══\n');
  
  for (const [name, entryId] of Object.entries(YOUR_TEAMS)) {
    const squad = results.squads[entryId];
    if (squad) {
      console.log(`${name}:`);
      console.log(`  Player IDs: [${squad.playerIds.join(', ')}]`);
      console.log('');
    }
  }
  
  // Analyze transactions
  console.log('\n═══ TRANSACTION ANALYSIS ═══\n');
  
  if (results.transactions && results.transactions.transactions) {
    const trans = results.transactions.transactions;
    console.log(`Total transactions: ${trans.length}`);
    
    // Count by type
    const byType = {};
    trans.forEach(t => {
      const kind = t.kind || 'unknown';
      byType[kind] = (byType[kind] || 0) + 1;
    });
    
    console.log('By type:', byType);
    
    // Check for trades
    const trades = trans.filter(t => 
      t.kind === 't' || 
      t.entry_2 !== undefined || 
      t.element_in_2 !== undefined
    );
    
    console.log(`\nTrades detected: ${trades.length}`);
    
    if (trades.length > 0) {
      console.log('\n✅ TRADE FOUND! Sample:');
      console.log(JSON.stringify(trades[0], null, 2));
    } else {
      console.log('\n⚠️ NO TRADES FOUND in transactions');
      console.log('\nChecking for trade-like fields...');
      
      // Show all unique fields in transactions
      const allFields = new Set();
      trans.forEach(t => Object.keys(t).forEach(k => allFields.add(k)));
      console.log('Fields in transactions:', Array.from(allFields).sort());
      
      // Show samples
      console.log('\nSample waiver:', trans.find(t => t.kind === 'w'));
      console.log('Sample free agent:', trans.find(t => t.kind === 'f'));
    }
  } else {
    console.log('❌ No transactions data');
  }
  
  // Check separate trades endpoint
  console.log('\n═══ SEPARATE TRADES ENDPOINT ═══\n');
  
  if (results.trades) {
    console.log('✅ Endpoint exists!');
    console.log('Structure:', Object.keys(results.trades));
    console.log('Full response:', results.trades);
    
    if (results.trades.trades && Array.isArray(results.trades.trades)) {
      console.log(`\nTrades found: ${results.trades.trades.length}`);
      if (results.trades.trades.length > 0) {
        console.log('Sample trade:');
        console.log(JSON.stringify(results.trades.trades[0], null, 2));
      }
    }
  } else {
    console.log('❌ Endpoint not available (this is normal for most leagues)');
  }
  
  // Compare to GW20 data (from user's JSON)
  console.log('\n═══ COMPARISON WITH GW20 DATA ═══\n');
  console.log('According to your GW20 JSON (2026-01-22):');
  console.log('  Saliba (6) was in: Hapoel Eliyahu (822133)');
  console.log('  Gabriel (5) was in: Johnny (827066)');
  console.log('');
  
  const salibaOwnerNow = Object.values(results.squads).find(s => s.playerIds.includes(6));
  const gabrielOwnerNow = Object.values(results.squads).find(s => s.playerIds.includes(5));
  
  console.log(`Now (GW${CURRENT_GW}):`);
  console.log(`  Saliba (6) is in: ${salibaOwnerNow ? `${salibaOwnerNow.name} (${Object.keys(results.squads).find(k => results.squads[k] === salibaOwnerNow)})` : 'UNKNOWN'}`);
  console.log(`  Gabriel (5) is in: ${gabrielOwnerNow ? `${gabrielOwnerNow.name} (${Object.keys(results.squads).find(k => results.squads[k] === gabrielOwnerNow)})` : 'UNKNOWN'}`);
  
  // Check if there was movement
  const salibaMovedEntry = Object.keys(results.squads).find(k => results.squads[k] === salibaOwnerNow);
  const gabrielMovedEntry = Object.keys(results.squads).find(k => results.squads[k] === gabrielOwnerNow);
  
  console.log('\n📊 TRADE ANALYSIS:');
  if (salibaMovedEntry !== '822133') {
    console.log(`  ✅ Saliba MOVED from 822133 to ${salibaMovedEntry}`);
  } else {
    console.log(`  ⚠️ Saliba still in same team (822133)`);
  }
  
  if (gabrielMovedEntry !== '827066') {
    console.log(`  ✅ Gabriel MOVED from 827066 to ${gabrielMovedEntry}`);
  } else {
    console.log(`  ⚠️ Gabriel still in same team (827066)`);
  }
  
  // Check for YOUR specific trade expectation
  console.log('\n🎯 YOUR EXPECTED TRADE:');
  console.log('  You (830139 or 822133) traded with Yoni (827066)');
  console.log('  You give: Saliba → You get: Gabriel');
  console.log('  Yoni gives: Gabriel → Yoni gets: Saliba');
  
  const yourTeamIds = [822133, 830139];
  const yourTeamHasGabriel = yourTeamIds.some(id => results.squads[id]?.playerIds.includes(5));
  const yoniHasSaliba = results.squads[827066]?.playerIds.includes(6);
  
  console.log('\n✅ Trade Verification:');
  console.log(`  You have Gabriel (5): ${yourTeamHasGabriel ? '✅ YES' : '❌ NO'}`);
  console.log(`  Yoni has Saliba (6): ${yoniHasSaliba ? '✅ YES' : '❌ NO'}`);
  
  if (yourTeamHasGabriel && yoniHasSaliba) {
    console.log('\n🎉 TRADE IS REFLECTED IN SQUADS! ✅');
  } else {
    console.log('\n⚠️ TRADE NOT YET REFLECTED (or different trade happened)');
  }
  
  // Final summary
  console.log('\n');
  console.log('═══════════════════════════════════════════════════════');
  console.log('📋 SUMMARY');
  console.log('═══════════════════════════════════════════════════════\n');
  
  console.log(`Saliba (6) current owner: ${salibaOwnerNow ? salibaOwnerNow.name : 'UNKNOWN'}`);
  console.log(`Gabriel (5) current owner: ${gabrielOwnerNow ? gabrielOwnerNow.name : 'UNKNOWN'}`);
  
  if (results.transactions) {
    const trans = results.transactions.transactions || [];
    const tradeCount = trans.filter(t => t.kind === 't' || t.entry_2).length;
    console.log(`\nTransactions fetched: ${trans.length}`);
    console.log(`Trades in transactions: ${tradeCount}`);
  }
  
  if (results.trades && results.trades.trades) {
    console.log(`Trades from /trades endpoint: ${results.trades.trades.length}`);
  }
  
  console.log('\n🔑 KEY INSIGHT:');
  if (yourTeamHasGabriel && yoniHasSaliba) {
    console.log('✅ Squad data already has your trade applied!');
    console.log('✅ We can trust squad snapshots as "source of truth"');
    console.log('✅ No need to track individual trades - just fetch fresh squads!');
  } else {
    console.log('⚠️ Current squad data may be stale or incomplete');
    console.log('⚠️ Need to check waiver pick timing to understand sync status');
  }
  
  console.log('\n═══════════════════════════════════════════════════════');
  console.log('✅ INSPECTION COMPLETE!');
  console.log('═══════════════════════════════════════════════════════');
  console.log('\n💡 Copy this ENTIRE output and share it!');
}

// Run the inspection
inspectFPL().catch(e => {
  console.error('❌ Error during inspection:', e);
});
