#!/usr/bin/env python3
"""
Update FPL squads with current GW22 data from FPL website
"""

import json
import duckdb
from pathlib import Path

# GW22 Squads from FPL website
GW22_SQUADS = {
    822203: {  # Roy's team
        'entry_name': "Roy's team",
        'short_name': 'rc',
        'players': [
            'Verbruggen', 'Hall', 'Collins', 'Kerkez', 'B.Fernandes', 'Wirtz',
            'Gordon', 'Anderson', 'Rodrigo', 'Bowen', 'Evanilson',
            'Donnarumma', 'Matheus N.', 'Šeško', 'Calafiori'
        ]
    },
    827275: {  # Hapoel Yehuda
        'entry_name': 'Hapoel Yehuda',
        'short_name': 'in',
        'players': [
            'Henderson', 'Tarkowski', 'Senesi', 'Van de Ven', 'Wilson',
            'Reijnders', 'Garner', 'Caicedo', 'Kolo Muani', 'Ekitiké', 'Thiago',
            'Petrović', 'Guéhi', 'Minteh', 'Gusto'
        ]
    },
    830139: {  # CHANGE NAME (IA1)
        'entry_name': 'CHANGE NAME',
        'short_name': 'IA1',
        'players': [
            'Sánchez', 'Romero', 'Thiaw', 'Van Hecke', 'White', 'Foden',
            'Palmer', 'Rogers', 'Szoboszlai', 'Ødegaard', 'Welbeck',
            'Kelleher', "O'Reilly", 'Mané', 'Barry'
        ]
    },
    827066: {  # Johnny
        'entry_name': 'Johnny',
        'short_name': 'YT',
        'players': [
            'Roefs', 'Saliba', 'Lacroix', 'James', 'Mukiele', 'Neto',
            'Bruno G.', 'Cherki', 'Cunha', 'Calvert-Lewin', 'Wissa',
            'Leno', 'Stach', 'Alderete', 'Igor Jesus'
        ]
    },
    829535: {  # Red Devils FC
        'entry_name': 'Red Devils FC',
        'short_name': 'nc',
        'players': [
            'A.Becker', 'J.Timber', 'Botman', 'Cucurella', 'Ballard',
            'Barnes', 'Saka', 'Gakpo', 'Tavernier', 'Gyökeres', 'Woltemade',
            'Martinez', 'Delap', 'Schade', 'Kayode'
        ]
    },
    822133: {  # Hapoel Eliyahu (IA)
        'entry_name': 'Hapoel Eliyahu',
        'short_name': 'IA',
        'players': [
            'Pickford', 'Chalobah', 'Gabriel', 'Cash', 'Andersen',
            'Casemiro', 'Rice', 'Gravenberch', 'Grealish', 'João Pedro', 'Kroupi.Jr',
            'Areola', 'O.Dango', 'Fofana', 'Taty'
        ]
    },
    830333: {  # McShaike's
        'entry_name': "McShaike's",
        'short_name': 'sg',
        'players': [
            'Pope', 'Mitchell', 'Konaté', 'Robinson', 'Richards',
            'Mbeumo', 'Enzo', 'Gibbs-White', 'Tolu', 'Mateta', 'Watkins',
            'Vicario', 'M.Salah', 'Ndiaye', 'Muñoz'
        ]
    },
    829475: {  # The Gunners
        'entry_name': 'The Gunners',
        'short_name': 'YR',
        'players': [
            'Raya', 'Konsa', 'Virgil', 'Pedro Porro', 'Frimpong',
            'E.Le Fée', 'Xhaka', 'Semenyo', 'Mitoma', 'Raúl', 'Haaland',
            'Lammens', 'Trossard', 'Aké', 'Strand Larsen'
        ]
    }
}

def match_player_name(target_name, all_players):
    """Match a player name from FPL website to player ID in database."""
    target_lower = target_name.lower().strip()
    
    # Direct web_name match
    for p in all_players:
        if p['web_name'].lower() == target_lower:
            return p['id']
    
    # Try last name match
    for p in all_players:
        if p['second_name'].lower() == target_lower:
            return p['id']
    
    # Try first name match
    for p in all_players:
        if p['first_name'].lower() == target_lower:
            return p['id']
    
    # Try partial match in web_name
    for p in all_players:
        if target_lower in p['web_name'].lower() or p['web_name'].lower() in target_lower:
            return p['id']
    
    # Try partial match in full name
    for p in all_players:
        full_name = f"{p['first_name']} {p['second_name']}".lower()
        if target_lower in full_name or full_name in target_lower:
            return p['id']
    
    # Special cases
    special_cases = {
        'b.fernandes': 'Bruno Fernandes',
        'bruno g.': 'Bruno Guimarães',
        'j.timber': 'Jurriën Timber',
        'a.becker': 'Alisson',
        'virgil': 'van Dijk',
        'pedro porro': 'Porro',
        'e.le fée': 'Le Fée',
        'raúl': 'Raúl Jiménez',
        'm.salah': 'Salah',
        'matheus n.': 'Matheus Nunes',
        'kroupi.jr': 'Kroupi',
        'o.dango': 'Dango',
        'joão pedro': 'João Pedro',
        'taty': 'Taty Castellanos',
        'šeško': 'Šeško',
        'o\'reilly': 'O\'Reilly'
    }
    
    if target_lower in special_cases:
        return match_player_name(special_cases[target_lower], all_players)
    
    return None

def main():
    print("═══ UPDATING FPL SQUADS WITH GW22 DATA ═══\n")
    
    # Load player data from JSON
    json_path = Path("fpl_league_data_2026-01-22.json")
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    all_players = data.get('bootstrap', {}).get('elements', [])
    print(f"Loaded {len(all_players)} players from bootstrap\n")
    
    # Connect to database (use the CORRECT path that the API uses!)
    db_path = Path("fpl_data.duckdb")  # Project root, not fpl_predictor/data/
    con = duckdb.connect(str(db_path))
    
    # Ensure database schema exists
    from fpl_predictor.data.database import init_schema
    init_schema(con)
    print("Database initialized\n")
    
    # Import bootstrap data first (players and teams) - directly without DataImporter
    print("Importing bootstrap data...")
    bootstrap = data.get('bootstrap', {})
    
    # Import teams
    teams = bootstrap.get('teams', [])
    for team in teams:
        con.execute("""
            INSERT OR REPLACE INTO pl_teams (
                id, name, short_name, code, strength_overall_home, strength_overall_away,
                strength_attack_home, strength_attack_away, strength_defence_home, strength_defence_away,
                position, played, won, drawn, lost, goals_for, goals_against, points, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, [
            team.get('id'), team.get('name'), team.get('short_name'), team.get('code'),
            team.get('strength_overall_home'), team.get('strength_overall_away'),
            team.get('strength_attack_home'), team.get('strength_attack_away'),
            team.get('strength_defence_home'), team.get('strength_defence_away'),
            team.get('position', 0), team.get('played', 0), team.get('win', 0),
            team.get('draw', 0), team.get('loss', 0),
            team.get('goals_for', 0) or team.get('team_goals_for', 0),
            team.get('goals_against', 0) or team.get('team_goals_against', 0),
            team.get('points', 0)
        ])
    
    # Import players
    players = bootstrap.get('elements', [])
    for player in players:
        con.execute("""
            INSERT OR REPLACE INTO pl_players (
                id, web_name, first_name, second_name, team_id, position,
                status, total_points, goals_scored, assists, clean_sheets,
                saves, bonus, minutes, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, [
            player.get('id'), player.get('web_name'), player.get('first_name'),
            player.get('second_name'), player.get('team'), player.get('element_type'),
            player.get('status', 'a'), player.get('total_points', 0),
            player.get('goals_scored', 0), player.get('assists', 0),
            player.get('clean_sheets', 0), player.get('saves', 0),
            player.get('bonus', 0), player.get('minutes', 0)
        ])
    
    con.commit()
    print("✅ Bootstrap data imported\n")
    
    # Import league entries
    print("Importing league entries...")
    league_entries = data.get('league', {}).get('league_entries', [])
    for entry in league_entries:
        entry_id = entry.get('entry_id')
        con.execute("""
            INSERT INTO fpl_entries (
                id, entry_id, entry_name, short_name,
                player_first_name, player_last_name
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (entry_id) DO UPDATE SET
                entry_name = excluded.entry_name,
                short_name = excluded.short_name,
                player_first_name = excluded.player_first_name,
                player_last_name = excluded.player_last_name
        """, [
            entry_id, entry_id,  # Use entry_id as id
            entry.get('entry_name'),
            entry.get('short_name'),
            entry.get('player_first_name'),
            entry.get('player_last_name')
        ])
    con.commit()
    print(f"✅ Imported {len(league_entries)} league entries\n")
    
    # Process GW22 squads
    print("═══ PROCESSING GW22 SQUADS ═══\n")
    
    # Clear existing GW22 data
    con.execute("DELETE FROM fpl_squads WHERE gameweek = 22")
    con.execute("DELETE FROM element_status")
    con.commit()
    
    total_matched = 0
    total_unmatched = 0
    
    for entry_id, squad_info in GW22_SQUADS.items():
        entry_name = squad_info['entry_name']
        players = squad_info['players']
        
        print(f"📋 {entry_name} ({entry_id})")
        
        matched_player_ids = []
        unmatched_names = []
        
        for idx, player_name in enumerate(players):
            player_id = match_player_name(player_name, all_players)
            
            if player_id:
                matched_player_ids.append((player_id, idx + 1))
                total_matched += 1
            else:
                unmatched_names.append(player_name)
                total_unmatched += 1
                print(f"  ⚠️ Could not match: {player_name}")
        
        # Insert matched players into fpl_squads
        for player_id, position in matched_player_ids:
            con.execute("""
                INSERT INTO fpl_squads (
                    entry_id, player_id, gameweek, squad_position,
                    is_captain, is_vice_captain
                ) VALUES (?, ?, 22, ?, FALSE, FALSE)
            """, [entry_id, player_id, position])
            
            # Also update element_status
            con.execute("""
                INSERT OR REPLACE INTO element_status (
                    element_id, owner_entry_id, status, in_squad, updated_at
                ) VALUES (?, ?, 'a', TRUE, CURRENT_TIMESTAMP)
            """, [player_id, entry_id])
        
        print(f"  ✅ Matched {len(matched_player_ids)}/15 players")
        if unmatched_names:
            print(f"  ❌ Unmatched: {', '.join(unmatched_names)}")
        print()
    
    con.commit()
    
    # Summary
    print("═══ SUMMARY ═══\n")
    print(f"Total players matched: {total_matched}")
    print(f"Total players unmatched: {total_unmatched}")
    print(f"Success rate: {total_matched / (total_matched + total_unmatched) * 100:.1f}%\n")
    
    # Verify specific players
    print("═══ VERIFICATION: CUNHA & CASEMIRO ═══\n")
    
    # Check Cunha
    cunha_owner = con.execute("""
        SELECT s.entry_id, e.entry_name, p.web_name
        FROM fpl_squads s
        JOIN fpl_entries e ON s.entry_id = e.entry_id
        JOIN pl_players p ON s.player_id = p.id
        WHERE p.web_name LIKE '%Cunha%' AND s.gameweek = 22
    """).fetchone()
    
    if cunha_owner:
        print(f"Cunha: {cunha_owner[1]} (Entry {cunha_owner[0]})")
        is_yours = cunha_owner[0] in [822133, 830139]
        print(f"  {'✅ YOUR TEAM' if is_yours else '❌ Not yours'}")
    else:
        print("Cunha: Not found in any squad")
    
    # Check Casemiro
    casemiro_owner = con.execute("""
        SELECT s.entry_id, e.entry_name, p.web_name
        FROM fpl_squads s
        JOIN fpl_entries e ON s.entry_id = e.entry_id
        JOIN pl_players p ON s.player_id = p.id
        WHERE p.web_name LIKE '%Casemiro%' AND s.gameweek = 22
    """).fetchone()
    
    if casemiro_owner:
        print(f"\nCasemiro: {casemiro_owner[1]} (Entry {casemiro_owner[0]})")
        is_yours = casemiro_owner[0] in [822133, 830139]
        print(f"  {'✅ YOUR TEAM' if is_yours else '❌ Not yours'}")
    else:
        print("\nCasemiro: Not found in any squad")
    
    con.close()
    print("\n✅ Database updated successfully!")

if __name__ == '__main__':
    main()
