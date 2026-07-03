# DB -> FIFA alignment — DRY RUN (no writes)

## Pool-level changes
- Position flips: **103**
- Renames to FIFA spelling: **95**
- Players added (FIFA-only): **246**
- Players dropped (not in FIFA, none owned): **10**

## Squad impact (the part that touches managers' teams)

### u_ilay
- **Position flips (affect GW1/GW2 points):**
    - Raphinha (BRA): FWD → MID
    - Brahim Diaz (MOR): FWD → MID
    - Tajon Buchanan (CAN): MID → FWD
- **Renames:** Nicolás González→Nico González
- **Rebalance (1 swap(s) to restore 2/5/5/3):**
    - DROP Obed Vargas (MEX MID)
    - ADD  José Fajardo (PAN FWD, FIFA price 4.7)

### u_yuval
- **Position flips (affect GW1/GW2 points):**
    - Rubén Vargas (SWI): FWD → MID
    - Vinicius Júnior (BRA): FWD → MID
- **Rebalance (2 swap(s) to restore 2/5/5/3):**
    - DROP Marwan Attia (EGY MID)
    - DROP Fabinho (BRA MID)
    - ADD  Agustín Álvarez (URU FWD, FIFA price 5.2)
    - ADD  Tete Yengi (AUS FWD, FIFA price 4.3)

### u_netanel
- **Position flips (affect GW1/GW2 points):**
    - Ar'jany Martha (CUW): MID → DEF
- **Rebalance (1 swap(s) to restore 2/5/5/3):**
    - DROP Ar'jany Martha (CUW DEF)
    - ADD  Malcom DaCosta (ECU MID, FIFA price 3.8)

### u_shay
- **Position flips (affect GW1/GW2 points):**
    - Lachlan Bayliss (NZL): FWD → MID
    - Nico Paz (ARG): FWD → MID
- **Rebalance (2 swap(s) to restore 2/5/5/3):**
    - DROP Lachlan Bayliss (NZL MID)
    - DROP Caleb Yirenkyi (GHA MID)
    - ADD  Guillermo Martínez (MEX FWD, FIFA price 4.7)
    - ADD  Kadir Barría (PAN FWD, FIFA price 4)

### u_nadav
- **Position flips (affect GW1/GW2 points):**
    - Riyad Mahrez (ALG): FWD → MID
- **Renames:** Alexander Sorloth→Alexander Sørloth, Alaa Al Hajji→Alaa Al Hejji, Yassine Gessime→Gessime Yassine
- **Rebalance (1 swap(s) to restore 2/5/5/3):**
    - DROP Alaa Al Hajji (SAU MID)
    - ADD  Cecilio Waterman (PAN FWD, FIFA price 5)

### u_roy
- **Position flips (affect GW1/GW2 points):**
    - Julio Enciso (PAR): FWD → MID
- **Renames:** Shahriar Moghanlou→Shahriyar Moghanlou
- **Rebalance (1 swap(s) to restore 2/5/5/3):**
    - DROP Ivan Bašić (BOS MID)
    - ADD  Sebastián Soria (QAT FWD, FIFA price 5.1)

