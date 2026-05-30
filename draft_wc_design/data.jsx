// =====================================================================
// WC26 Fantasy Draft — Mock Data
// State: GW6 finalised. SF seeded, GW7 incoming.
// League: 7 managers, 4 qualifiers (seeds 1v4, 2v3 at GW7).
// =====================================================================

// ---------- Groups & Teams ----------
// 12 groups, 4 teams each. Mock final standings (top 2 + best 8 thirds advance).
// Group colour matches CSS var --grp-X.

const TEAMS = [
  // Group A
  { id: "MEX", name: "Mexico",        grp: "A", flag: ["#006847","#fff","#ce1126"], elim: false, pos: 1 },
  { id: "CAN", name: "Canada",        grp: "A", flag: ["#fff","#ff0000","#fff"],     elim: false, pos: 2, vert: ["#ff0000","#fff","#ff0000"] },
  { id: "MAR", name: "Morocco",       grp: "A", flag: ["#c1272d","#c1272d","#c1272d"], elim: true,  pos: 3 },
  { id: "UZB", name: "Uzbekistan",    grp: "A", flag: ["#1eb53a","#fff","#0099b5"], elim: true,  pos: 4 },
  // Group B
  { id: "ARG", name: "Argentina",     grp: "B", flag: ["#74acdf","#fff","#74acdf"], elim: false, pos: 1 },
  { id: "JPN", name: "Japan",         grp: "B", flag: ["#fff","#fff","#fff"], elim: false, pos: 2, dot: "#bc002d" },
  { id: "ITA", name: "Italy",         grp: "B", vert: ["#008c45","#fff","#cd212a"], elim: true,  pos: 3 },
  { id: "EGY", name: "Egypt",         grp: "B", flag: ["#ce1126","#fff","#000"], elim: false, pos: 3, bestThird: true },
  // Group C
  { id: "BRA", name: "Brazil",        grp: "C", flag: ["#009c3b","#ffdf00","#009c3b"], elim: false, pos: 1 },
  { id: "POR", name: "Portugal",      grp: "C", flag: ["#006600","#006600","#ff0000"], elim: false, pos: 2 },
  { id: "GHA", name: "Ghana",         grp: "C", flag: ["#ce1126","#ffd700","#006b3f"], elim: true,  pos: 3 },
  { id: "AUS", name: "Australia",     grp: "C", flag: ["#0050a3","#0050a3","#0050a3"], elim: true,  pos: 4 },
  // Group D
  { id: "FRA", name: "France",        grp: "D", vert: ["#002654","#fff","#ce1126"], elim: false, pos: 1 },
  { id: "CRO", name: "Croatia",       grp: "D", flag: ["#ff0000","#fff","#171796"], elim: false, pos: 2 },
  { id: "NGA", name: "Nigeria",       grp: "D", vert: ["#008751","#fff","#008751"], elim: false, pos: 3, bestThird: true },
  { id: "KSA", name: "Saudi Arabia",  grp: "D", flag: ["#006c35","#006c35","#006c35"], elim: true, pos: 4 },
  // Group E
  { id: "ENG", name: "England",       grp: "E", flag: ["#fff","#fff","#fff"], dot: "#ce1124", elim: false, pos: 1 },
  { id: "ECU", name: "Ecuador",       grp: "E", flag: ["#ffd100","#0033a0","#ed1c24"], elim: false, pos: 2 },
  { id: "IRN", name: "Iran",          grp: "E", flag: ["#239f40","#fff","#da0000"], elim: true,  pos: 3 },
  { id: "ALG", name: "Algeria",       grp: "E", flag: ["#fff","#fff","#006233"], elim: true,  pos: 4 },
  // Group F
  { id: "GER", name: "Germany",       grp: "F", flag: ["#000","#dd0000","#ffce00"], elim: false, pos: 1 },
  { id: "BEL", name: "Belgium",       grp: "F", vert: ["#000","#fdda24","#ef3340"], elim: false, pos: 2 },
  { id: "USA", name: "United States", grp: "F", flag: ["#b22234","#fff","#3c3b6e"], elim: false, pos: 3, bestThird: true },
  { id: "JOR", name: "Jordan",        grp: "F", flag: ["#000","#fff","#007a3d"], elim: true,  pos: 4 },
  // Group G
  { id: "ESP", name: "Spain",         grp: "G", flag: ["#aa151b","#f1bf00","#aa151b"], elim: false, pos: 1 },
  { id: "SEN", name: "Senegal",       grp: "G", vert: ["#00853f","#fdef42","#e31b23"], elim: false, pos: 2 },
  { id: "POL", name: "Poland",        grp: "G", flag: ["#fff","#fff","#dc143c"], elim: true, pos: 3 },
  { id: "TUN", name: "Tunisia",       grp: "G", flag: ["#e70013","#fff","#e70013"], elim: true,  pos: 4 },
  // Group H
  { id: "NED", name: "Netherlands",   grp: "H", flag: ["#ae1c28","#fff","#21468b"], elim: false, pos: 1 },
  { id: "URU", name: "Uruguay",       grp: "H", flag: ["#7b9ee3","#fff","#7b9ee3"], elim: false, pos: 2 },
  { id: "CRC", name: "Costa Rica",    grp: "H", flag: ["#002b7f","#fff","#ce1126"], elim: true,  pos: 3 },
  { id: "QAT", name: "Qatar",         grp: "H", flag: ["#8a1538","#8a1538","#8a1538"], elim: true,  pos: 4 },
  // Group I
  { id: "COL", name: "Colombia",      grp: "I", flag: ["#fcd116","#003893","#ce1126"], elim: false, pos: 1 },
  { id: "KOR", name: "South Korea",   grp: "I", flag: ["#fff","#fff","#fff"], dot: "#cd2e3a", elim: false, pos: 2 },
  { id: "CHI", name: "Chile",         grp: "I", flag: ["#fff","#d52b1e","#0039a6"], elim: false, pos: 3, bestThird: true },
  { id: "OMA", name: "Oman",          grp: "I", flag: ["#db161b","#fff","#008000"], elim: true,  pos: 4 },
  // Group J
  { id: "DEN", name: "Denmark",       grp: "J", flag: ["#c8102e","#c8102e","#c8102e"], elim: false, pos: 1 },
  { id: "CIV", name: "Côte d'Ivoire", grp: "J", vert: ["#ff8200","#fff","#009a44"], elim: false, pos: 2 },
  { id: "SCO", name: "Scotland",      grp: "J", flag: ["#005eb8","#005eb8","#005eb8"], elim: false, pos: 3, bestThird: true },
  { id: "NZL", name: "New Zealand",   grp: "J", flag: ["#012169","#012169","#012169"], elim: true, pos: 4 },
  // Group K
  { id: "SUI", name: "Switzerland",   grp: "K", flag: ["#dc291e","#dc291e","#dc291e"], elim: false, pos: 1 },
  { id: "CMR", name: "Cameroon",      grp: "K", vert: ["#007a5e","#ce1126","#fcd116"], elim: false, pos: 2 },
  { id: "PAR", name: "Paraguay",      grp: "K", flag: ["#d52b1e","#fff","#0038a8"], elim: true, pos: 3 },
  { id: "CUR", name: "Curaçao",       grp: "K", flag: ["#002b7f","#002b7f","#fff"], elim: true, pos: 4 },
  // Group L
  { id: "POR2",name: "Türkiye",       grp: "L", flag: ["#e30a17","#e30a17","#e30a17"], elim: false, pos: 1 },
  { id: "MEX2",name: "Peru",          grp: "L", flag: ["#d91023","#fff","#d91023"], elim: false, pos: 2 },
  { id: "VEN", name: "Venezuela",     grp: "L", flag: ["#ffcc00","#003da5","#cf142b"], elim: true, pos: 3 },
  { id: "HAI", name: "Haiti",         grp: "L", flag: ["#00209f","#d21034","#d21034"], elim: true, pos: 4 },
];

const TEAM_MAP = Object.fromEntries(TEAMS.map(t => [t.id, t]));

// ---------- Players ----------
// Position: 1=GK, 2=DEF, 3=MID, 4=FWD
// Compact list — enough to populate squads, draft, browser.
const POS_NAMES = { 1: "GK", 2: "DEF", 3: "MID", 4: "FWD" };

const PLAYERS = [
  // ----- Brazil -----
  { id: "p_alisson", name: "Alisson",   pos: 1, team: "BRA", pts: 38, dr: 28 },
  { id: "p_marquinhos", name: "Marquinhos", pos: 2, team: "BRA", pts: 24, dr: 41 },
  { id: "p_militao", name: "Militão",  pos: 2, team: "BRA", pts: 19, dr: 84 },
  { id: "p_vinijr", name: "Vinícius Jr", pos: 4, team: "BRA", pts: 52, dr: 3 },
  { id: "p_rodrygo", name: "Rodrygo",   pos: 3, team: "BRA", pts: 31, dr: 19 },
  { id: "p_neymar", name: "Neymar",    pos: 3, team: "BRA", pts: 28, dr: 8 },
  { id: "p_endrick", name: "Endrick",   pos: 4, team: "BRA", pts: 18, dr: 47 },

  // ----- Argentina -----
  { id: "p_emi_martinez", name: "E. Martínez", pos: 1, team: "ARG", pts: 33, dr: 14 },
  { id: "p_lisandro", name: "L. Martínez", pos: 2, team: "ARG", pts: 22, dr: 38 },
  { id: "p_otamendi", name: "Otamendi",  pos: 2, team: "ARG", pts: 17, dr: 92 },
  { id: "p_demaria", name: "Di María",   pos: 3, team: "ARG", pts: 25, dr: 33 },
  { id: "p_alvarez", name: "J. Álvarez", pos: 4, team: "ARG", pts: 41, dr: 6 },
  { id: "p_messi", name: "Messi",     pos: 3, team: "ARG", pts: 48, dr: 1 },
  { id: "p_macallister", name: "Mac Allister", pos: 3, team: "ARG", pts: 27, dr: 22 },

  // ----- France -----
  { id: "p_maignan", name: "Maignan",   pos: 1, team: "FRA", pts: 29, dr: 25 },
  { id: "p_kounde", name: "Koundé",    pos: 2, team: "FRA", pts: 21, dr: 51 },
  { id: "p_saliba", name: "Saliba",    pos: 2, team: "FRA", pts: 26, dr: 32 },
  { id: "p_tchouameni", name: "Tchouaméni", pos: 3, team: "FRA", pts: 19, dr: 76 },
  { id: "p_mbappe", name: "Mbappé",    pos: 4, team: "FRA", pts: 49, dr: 2 },
  { id: "p_dembele", name: "O. Dembélé", pos: 3, team: "FRA", pts: 34, dr: 11 },
  { id: "p_kolo_muani", name: "Kolo Muani", pos: 4, team: "FRA", pts: 23, dr: 43 },

  // ----- England -----
  { id: "p_pickford", name: "Pickford",  pos: 1, team: "ENG", pts: 25, dr: 42 },
  { id: "p_stones", name: "Stones",    pos: 2, team: "ENG", pts: 20, dr: 65 },
  { id: "p_walker", name: "Walker",    pos: 2, team: "ENG", pts: 18, dr: 88 },
  { id: "p_bellingham", name: "Bellingham", pos: 3, team: "ENG", pts: 42, dr: 5 },
  { id: "p_foden", name: "Foden",     pos: 3, team: "ENG", pts: 36, dr: 9 },
  { id: "p_saka", name: "Saka",      pos: 3, team: "ENG", pts: 33, dr: 13 },
  { id: "p_kane", name: "Kane",      pos: 4, team: "ENG", pts: 44, dr: 4 },

  // ----- Spain -----
  { id: "p_simon", name: "U. Simón",  pos: 1, team: "ESP", pts: 27, dr: 36 },
  { id: "p_lenormand", name: "Le Normand", pos: 2, team: "ESP", pts: 23, dr: 44 },
  { id: "p_carvajal", name: "Carvajal",  pos: 2, team: "ESP", pts: 21, dr: 56 },
  { id: "p_pedri", name: "Pedri",     pos: 3, team: "ESP", pts: 32, dr: 17 },
  { id: "p_yamal", name: "L. Yamal",  pos: 3, team: "ESP", pts: 38, dr: 7 },
  { id: "p_rodri", name: "Rodri",     pos: 3, team: "ESP", pts: 22, dr: 39 },
  { id: "p_morata", name: "Morata",    pos: 4, team: "ESP", pts: 24, dr: 35 },

  // ----- Germany -----
  { id: "p_terstegen", name: "ter Stegen", pos: 1, team: "GER", pts: 26, dr: 49 },
  { id: "p_rudiger", name: "Rüdiger",   pos: 2, team: "GER", pts: 22, dr: 53 },
  { id: "p_kimmich", name: "Kimmich",   pos: 2, team: "GER", pts: 28, dr: 24 },
  { id: "p_musiala", name: "Musiala",   pos: 3, team: "GER", pts: 35, dr: 10 },
  { id: "p_wirtz", name: "Wirtz",     pos: 3, team: "GER", pts: 30, dr: 18 },
  { id: "p_havertz", name: "Havertz",   pos: 4, team: "GER", pts: 21, dr: 46 },
  { id: "p_fullkrug", name: "Füllkrug",  pos: 4, team: "GER", pts: 17, dr: 71 },

  // ----- Netherlands -----
  { id: "p_verbruggen", name: "Verbruggen", pos: 1, team: "NED", pts: 24, dr: 58 },
  { id: "p_vandijk", name: "Van Dijk",  pos: 2, team: "NED", pts: 26, dr: 27 },
  { id: "p_aké", name: "Aké",       pos: 2, team: "NED", pts: 19, dr: 78 },
  { id: "p_gakpo", name: "Gakpo",     pos: 3, team: "NED", pts: 29, dr: 21 },
  { id: "p_xavi", name: "X. Simons", pos: 3, team: "NED", pts: 31, dr: 16 },
  { id: "p_depay", name: "Depay",     pos: 4, team: "NED", pts: 25, dr: 30 },

  // ----- Portugal -----
  { id: "p_costa", name: "D. Costa",   pos: 1, team: "POR", pts: 22, dr: 67 },
  { id: "p_dias", name: "R. Dias",    pos: 2, team: "POR", pts: 24, dr: 37 },
  { id: "p_canc", name: "Cancelo",   pos: 2, team: "POR", pts: 22, dr: 50 },
  { id: "p_bernardo", name: "B. Silva",  pos: 3, team: "POR", pts: 33, dr: 15 },
  { id: "p_bruno", name: "B. Fernandes", pos: 3, team: "POR", pts: 30, dr: 20 },
  { id: "p_ronaldo", name: "Ronaldo",   pos: 4, team: "POR", pts: 27, dr: 26 },
  { id: "p_leao", name: "Leão",      pos: 3, team: "POR", pts: 25, dr: 29 },

  // ----- Belgium -----
  { id: "p_courtois", name: "Courtois",  pos: 1, team: "BEL", pts: 28, dr: 40 },
  { id: "p_debruyne", name: "De Bruyne", pos: 3, team: "BEL", pts: 36, dr: 12 },
  { id: "p_lukaku", name: "Lukaku",    pos: 4, team: "BEL", pts: 22, dr: 45 },

  // ----- Croatia -----
  { id: "p_modric", name: "Modrić",   pos: 3, team: "CRO", pts: 26, dr: 31 },
  { id: "p_kovacic", name: "Kovačić",  pos: 3, team: "CRO", pts: 18, dr: 81 },
  { id: "p_kramaric", name: "Kramarić", pos: 4, team: "CRO", pts: 17, dr: 95 },

  // ----- USA -----
  { id: "p_pulisic", name: "Pulisic",  pos: 3, team: "USA", pts: 27, dr: 34 },
  { id: "p_mckennie", name: "McKennie", pos: 3, team: "USA", pts: 16, dr: 102 },
  { id: "p_balogun", name: "Balogun",  pos: 4, team: "USA", pts: 19, dr: 60 },
  { id: "p_adams", name: "Adams",    pos: 3, team: "USA", pts: 14, dr: 118 },

  // ----- Mexico -----
  { id: "p_ochoa", name: "Ochoa",    pos: 1, team: "MEX", pts: 21, dr: 72 },
  { id: "p_alvarez_e", name: "E. Álvarez", pos: 3, team: "MEX", pts: 23, dr: 48 },
  { id: "p_jimenez", name: "Jiménez",  pos: 4, team: "MEX", pts: 20, dr: 61 },

  // ----- Eliminated nations (still on rosters until window) -----
  { id: "p_donnarumma", name: "Donnarumma", pos: 1, team: "ITA", pts: 12, dr: 23, elim: true },
  { id: "p_barella", name: "Barella",   pos: 3, team: "ITA", pts: 9,  dr: 52, elim: true },
  { id: "p_hakimi", name: "Hakimi",    pos: 2, team: "MAR", pts: 14, dr: 28, elim: true },
  { id: "p_brozovic", name: "—",        pos: 3, team: "ITA", pts: 6,  dr: 90, elim: true },
  { id: "p_zielinski", name: "Zieliński", pos: 3, team: "POL", pts: 10, dr: 66, elim: true },
  { id: "p_szczesny", name: "Szczęsny",  pos: 1, team: "POL", pts: 13, dr: 80, elim: true },

  // ----- Senegal / Africa depth -----
  { id: "p_mendy", name: "É. Mendy",  pos: 1, team: "SEN", pts: 22, dr: 73 },
  { id: "p_koulibaly", name: "Koulibaly", pos: 2, team: "SEN", pts: 18, dr: 86 },
  { id: "p_sarr", name: "I. Sarr",   pos: 3, team: "SEN", pts: 17, dr: 99 },

  // ----- Switzerland -----
  { id: "p_sommer", name: "Sommer",    pos: 1, team: "SUI", pts: 19, dr: 91 },
  { id: "p_xhaka", name: "Xhaka",     pos: 3, team: "SUI", pts: 20, dr: 64 },

  // ----- Denmark -----
  { id: "p_eriksen", name: "Eriksen",   pos: 3, team: "DEN", pts: 22, dr: 55 },
  { id: "p_hojlund", name: "Højlund",   pos: 4, team: "DEN", pts: 18, dr: 79 },
  { id: "p_schmeichel", name: "Schmeichel", pos: 1, team: "DEN", pts: 17, dr: 100 },

  // ----- Colombia / SA -----
  { id: "p_jrodriguez", name: "J. Rodríguez", pos: 3, team: "COL", pts: 31, dr: 33 },
  { id: "p_diaz", name: "L. Díaz",   pos: 3, team: "COL", pts: 29, dr: 25 },

  // ----- Australia / Asia depth + fillers -----
  { id: "p_mitoma", name: "Mitoma",    pos: 3, team: "JPN", pts: 21, dr: 57 },
  { id: "p_kubo", name: "T. Kubo",   pos: 3, team: "JPN", pts: 19, dr: 70 },
  { id: "p_kamada", name: "Kamada",    pos: 3, team: "JPN", pts: 14, dr: 115 },

  // ----- Korea -----
  { id: "p_sonhm", name: "Son",       pos: 3, team: "KOR", pts: 28, dr: 23 },
  { id: "p_leekm", name: "K. Lee",    pos: 3, team: "KOR", pts: 15, dr: 110 },

  // ----- Uruguay -----
  { id: "p_nunez", name: "D. Núñez",  pos: 4, team: "URU", pts: 23, dr: 54 },
  { id: "p_valverde", name: "Valverde",  pos: 3, team: "URU", pts: 26, dr: 30 },
];

const PLAYER_MAP = Object.fromEntries(PLAYERS.map(p => [p.id, p]));

// ---------- Managers (10) ----------
// "you" = ilay_me. Indices used for snake draft order.
const MANAGERS = [
  { uid: "u_roy",    name: "Roy",     team: "La Liga Loca",   flag: "ESP", draftPos: 1, waiverPri: 7 },
  { uid: "u_yonatan",name: "Yonatan", team: "Tiki-Taka FC",   flag: "ARG", draftPos: 2, waiverPri: 6 },
  { uid: "u_nadav",  name: "Nadav",   team: "Red Devils 2026",flag: "BRA", draftPos: 3, waiverPri: 5 },
  { uid: "u_yuval",  name: "Yuval",   team: "The Gunners",    flag: "ENG", draftPos: 4, waiverPri: 4 },
  { uid: "u_ido",    name: "Ido",     team: "Tel Aviv United",flag: "FRA", draftPos: 5, waiverPri: 3 },
  { uid: "u_shai",   name: "Shai",    team: "McShaike's XI",  flag: "MEX", draftPos: 6, waiverPri: 2 },
  { uid: "u_me",     name: "Ilay (you)", team: "Hapoel Eliyahu", flag: "POR", draftPos: 7, waiverPri: 1 },
];

let ME = "u_me";

// ---------- Final group-phase H2H standings (after GW3) ----------
// Sorted by hpts → fpts. Top 8 qualify for KO.
const STANDINGS = [
  { uid: "u_roy",    rank: 1, hw: 5, hd: 0, hl: 1, hpts: 15, fpts: 382, mv: 0, bonusPoints: 12 },
  { uid: "u_yonatan",rank: 2, hw: 4, hd: 0, hl: 2, hpts: 12, fpts: 361, mv: 1, bonusPoints: 10 },
  { uid: "u_me",     rank: 3, hw: 3, hd: 0, hl: 3, hpts: 9, fpts: 379, mv: -2, ptsSeed: true, bonusPoints: 15 },
  { uid: "u_ido",    rank: 4, hw: 3, hd: 0, hl: 3, hpts: 9, fpts: 368, mv: 0, ptsSeed: true, bonusPoints: 9 },
  // — Qualification line —
  { uid: "u_nadav",  rank: 5, hw: 3, hd: 0, hl: 3, hpts: 9, fpts: 354, mv: -1, knockedOut: true, bonusPoints: 8 },
  { uid: "u_yuval",  rank: 6, hw: 2, hd: 0, hl: 4, hpts: 6, fpts: 340, mv: 1, knockedOut: true, bonusPoints: 7 },
  { uid: "u_shai",   rank: 7, hw: 1, hd: 0, hl: 5, hpts: 3, fpts: 310, mv: -1, knockedOut: true, bonusPoints: 5 },
];

// ---------- KO Bracket — seeded for GW4 (Quarter-Finals) ----------
// Seeds 1–4 = top H2H, 5–8 = best points of remaining
const BRACKET = {
  sf: [
    { id: "sf1", home: "u_roy", away: "u_ido", homeSeed: 1, awaySeed: 4, gw: 7 },
    { id: "sf2", home: "u_yonatan", away: "u_me", homeSeed: 2, awaySeed: 3, gw: 7 },
  ],
  final: [{ id: "f1", home: null, away: null, homeSrc: "sf1", awaySrc: "sf2", gw: 8 }],
};

// ---------- My Squad (15 players) ----------
const MY_SQUAD_IDS = [
  // GK ×2
  "p_costa", "p_donnarumma",     // ITA goalie eliminated 🚨
  // DEF ×5
  "p_dias", "p_kounde", "p_walker", "p_hakimi", "p_canc",  // hakimi eliminated 🚨
  // MID ×5
  "p_bruno", "p_bellingham", "p_musiala", "p_yamal", "p_zielinski",  // zielinski elim 🚨
  // FWD ×3
  "p_ronaldo", "p_mbappe", "p_kane",
];

// Starting XI from squad + bench (formation 1-4-4-2)
const MY_LINEUP_GW3 = {
  starting: [
    "p_costa",                                      // GK
    "p_dias", "p_kounde", "p_walker", "p_hakimi",   // DEF
    "p_bruno", "p_bellingham", "p_musiala", "p_yamal", // MID
    "p_mbappe", "p_kane",                           // FWD
  ],
  bench: ["p_donnarumma", "p_canc", "p_zielinski", "p_ronaldo"],
  formation: [1, 4, 4, 2],
  autoSubs: [{ in: "p_canc", out: "p_walker" }],
};

// GW3 points breakdown — per player
const GW3_POINTS = {
  p_costa: 6, p_donnarumma: 0,
  p_dias: 7, p_kounde: 4, p_walker: 1, p_hakimi: 2, p_canc: 5,
  p_bruno: 9, p_bellingham: 12, p_musiala: 8, p_yamal: 14, p_zielinski: 0,
  p_ronaldo: 11, p_mbappe: 7, p_kane: 4,
};

// Other managers' GW3 totals (so H2H makes sense)
const GW3_TOTALS = {
  u_roy: 78, u_yonatan: 65, u_nadav: 71, u_yuval: 62,
  u_ido: 69, u_shai: 48, u_me: 65, u_dor: 73, u_omer: 56, u_eyal: 41,
};

// ---------- GW3 H2H schedule (matchups) ----------
const SCHEDULE = {
  1: [
    ["u_roy","u_shai"], ["u_yonatan","u_me"], ["u_nadav","u_ido"]
  ],
  2: [
    ["u_roy","u_me"], ["u_yonatan","u_ido"], ["u_nadav","u_yuval"]
  ],
  3: [
    ["u_roy","u_ido"], ["u_yonatan","u_yuval"], ["u_me","u_shai"]
  ],
  4: [
    ["u_roy","u_yuval"], ["u_yonatan","u_nadav"], ["u_ido","u_shai"]
  ],
  5: [
    ["u_roy","u_nadav"], ["u_yuval","u_shai"], ["u_me","u_ido"]
  ],
  6: [],
};

// ---------- Fixtures: GW4 (Round of 32, July 1–4) ----------
const WC_FIXTURES_GW4 = [
  { day: "Wed 1 Jul", time: "16:00", home: "ESP", away: "JPN", venue: "Mexico City", live: false },
  { day: "Wed 1 Jul", time: "20:00", home: "ARG", away: "ECU", venue: "Atlanta",     live: false },
  { day: "Thu 2 Jul", time: "16:00", home: "FRA", away: "POR2",venue: "Toronto",     live: false },
  { day: "Thu 2 Jul", time: "20:00", home: "ENG", away: "URU", venue: "Dallas",      live: false },
  { day: "Fri 3 Jul", time: "16:00", home: "BRA", away: "USA", venue: "Houston",     live: false },
  { day: "Fri 3 Jul", time: "20:00", home: "NED", away: "EGY", venue: "New York",    live: false },
  { day: "Sat 4 Jul", time: "16:00", home: "GER", away: "MEX2",venue: "Los Angeles", live: false },
  { day: "Sat 4 Jul", time: "20:00", home: "COL", away: "KOR", venue: "Miami",       live: false },
];

// ---------- Transfer window state ----------
const WINDOW = {
  number: 3,
  label: "WINDOW 3 · The Big One",
  opensAt: "Sun 26 Jun, 22:00",
  closesAt: "Wed 1 Jul, 16:00",
  hoursLeft: 36,
  freeTransfers: 2,
  used: 0,
  state: "open",
};

// ---------- Waiver claims (pending — my team) ----------
const MY_WAIVERS = [
  { id: "w1", playerIn: "p_alvarez", playerOut: "p_zielinski", priority: 4, gw: 4, status: "pending" },
  { id: "w2", playerIn: "p_pickford", playerOut: "p_donnarumma", priority: 4, gw: 4, status: "pending" },
];

// Top free-agents pool (sample)
const FREE_AGENTS = [
  "p_alvarez", "p_pickford", "p_emi_martinez", "p_modric", "p_pulisic",
  "p_diaz", "p_nunez", "p_valverde", "p_jrodriguez", "p_mitoma",
  "p_courtois", "p_xavi", "p_endrick", "p_sarr", "p_eriksen",
].map(id => PLAYER_MAP[id]).filter(Boolean);

// ---------- Trades ----------
const TRADES_INBOX = [
  {
    id: "t1",
    proposer: "u_dor",
    target: "u_me",
    proposerPlayers: ["p_kane"],   // they offer
    targetPlayers: ["p_mbappe"],   // they want
    status: "pending",
    createdAt: "2h ago",
    message: "yo, swap Mbappé for Kane? both R32 friendly fixtures.",
  },
];
const TRADES_OUTBOX = [
  {
    id: "t2",
    proposer: "u_me",
    target: "u_yonatan",
    proposerPlayers: ["p_zielinski"],
    targetPlayers: ["p_messi"],
    status: "pending",
    createdAt: "30m ago",
    message: "longshot — Zieliński (elim) + I'll pick up Yamal for you on waivers",
  },
];

// ---------- Draft state (for Draft Room) ----------
// Snapshot: round 2 pick 4 (manager u_yuval on the clock)
const DRAFT_STATE = {
  round: 2,
  pickOverall: 14,
  pickInRound: 4,        // snake: even rounds reverse
  onTheClock: "u_yuval",
  totalRounds: 15,
  totalPicks: 150,
  pickTimer: 60,
  secondsLeft: 38,
  isMyTurn: false,
};

const DRAFT_HISTORY = [
  // Round 1 (1–10) — original order
  { round: 1, overall: 1,  uid: "u_roy",    playerId: "p_mbappe"     },
  { round: 1, overall: 2,  uid: "u_yonatan",playerId: "p_messi"      },
  { round: 1, overall: 3,  uid: "u_nadav",  playerId: "p_vinijr"     },
  { round: 1, overall: 4,  uid: "u_yuval",  playerId: "p_kane"       },
  { round: 1, overall: 5,  uid: "u_ido",    playerId: "p_bellingham" },
  { round: 1, overall: 6,  uid: "u_shai",   playerId: "p_alvarez"    },
  { round: 1, overall: 7,  uid: "u_me",     playerId: "p_yamal"      },
  { round: 1, overall: 8,  uid: "u_dor",    playerId: "p_foden"      },
  { round: 1, overall: 9,  uid: "u_omer",   playerId: "p_dembele"    },
  { round: 1, overall: 10, uid: "u_eyal",   playerId: "p_musiala"    },
  // Round 2 (11–20) — reversed
  { round: 2, overall: 11, uid: "u_eyal",   playerId: "p_saka"       },
  { round: 2, overall: 12, uid: "u_omer",   playerId: "p_debruyne"   },
  { round: 2, overall: 13, uid: "u_dor",    playerId: "p_bruno"      },
  // … u_yuval is now on the clock at #14
];

// ---------- Tournament config ----------
const TOURNAMENT = {
  currentGw: 7,
  status: "knockout",        // we just finished group → knockout begins
  season: 2026,
  gwDates: {
    1: { wcRound: "Group Stage · MD1", start: "Jun 11", end: "Jun 15", lockAt: "Jun 11 18:00" },
    2: { wcRound: "Group Stage · MD2", start: "Jun 16", end: "Jun 21", lockAt: "Jun 16 18:00" },
    3: { wcRound: "Group Stage · MD3", start: "Jun 22", end: "Jun 26", lockAt: "Jun 22 18:00" },
    4: { wcRound: "Group Stage · MD4", start: "Jun 27", end: "Jun 30", lockAt: "Jun 27 18:00" },
    5: { wcRound: "Group Stage · MD5", start: "Jul 1",  end: "Jul 5",  lockAt: "Jul 1 18:00" },
    6: { wcRound: "Group Stage · MD6", start: "Jul 6",  end: "Jul 10", lockAt: "Jul 6 18:00" },
    7: { wcRound: "Semi-Finals",       start: "Jul 14", end: "Jul 15", lockAt: "Jul 14 18:00" },
    8: { wcRound: "Final",             start: "Jul 18", end: "Jul 19", lockAt: "Jul 18 18:00" },
  },
};

// ---------- League config ----------
const LEAGUE = {
  id: "lg_clasico",
  name: "El Clásico Friends",
  inviteCode: "WC26-Q7XN",
  size: 7,
  knockoutStartGw: 7,
  leaguePhaseGws: [1, 2, 3, 4, 5, 6],
  knockoutQualifiers: 4,
  pickTimer: 60,
  tradeApproval: "vote",
  admin: "u_roy",
};

// ---------- Helpers ----------
const managerById = uid => {
  if (!uid) return undefined;
  return MANAGERS.find(m => m.uid === uid) || {
    uid: uid,
    name: uid === ME ? (window._auth?.currentUser?.displayName || "Me") : "Manager",
    team: uid === ME ? "My Team" : "Opponent XI",
    flag: "GER",
    draftPos: 99,
    waiverPri: 99
  };
};
const playerById  = id => {
  if (!id) return undefined;
  const activeMap = window.PLAYER_MAP || PLAYER_MAP;
  return activeMap[id] || {
    id: id,
    name: "Player " + String(id).replace("p_", ""),
    pos: 3,
    team: "GER",
    pts: 0,
    dr: 999
  };
};
const teamById    = id => {
  if (!id) return undefined;
  return TEAM_MAP[id] || {
    id: id,
    name: id || "Unknown Team",
    grp: "A",
    flag: ["#ccc", "#fff", "#ccc"],
    elim: false,
    pos: 4
  };
};

// expose globally
Object.assign(window, {
  TEAMS, TEAM_MAP, PLAYERS, PLAYER_MAP, POS_NAMES,
  MANAGERS, ME, STANDINGS, BRACKET,
  MY_SQUAD_IDS, MY_LINEUP_GW3, GW3_POINTS, GW3_TOTALS,
  SCHEDULE, WC_FIXTURES_GW4, WINDOW, MY_WAIVERS, FREE_AGENTS,
  TRADES_INBOX, TRADES_OUTBOX, DRAFT_STATE, DRAFT_HISTORY,
  TOURNAMENT, LEAGUE,
  managerById, playerById, teamById,
});
